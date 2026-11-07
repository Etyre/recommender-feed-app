"""Pipeline orchestrator for the Recommender Feed. One code path for scheduled (launchd)
and manual (UI Refresh button) runs; invoked as `python -m app.pipeline`.

Stages: fetch -> extract -> triage -> discovery -> extract/triage (discovered) -> rank ->
profile -> interview -> backup. Per-stage failures mark the run 'partial'; later stages
still run with what's available. If the model contacts Eli (see services/llm.py), the
remaining LLM stages are skipped; backup still runs.

Config and data: FEEDAPP_DATA_DIR, else the sibling ../data of the checkout (feed.db,
.env with ANTHROPIC_API_KEY, backups/, pipeline.lock). Logs: every line this process
prints is timestamped and also appended to ~/Library/Logs/recommender-feed.log (launchd
sends stdout/stderr there too). Run state lives in the pipeline_runs table."""
from __future__ import annotations

import fcntl
import json
import os
import sys
import time
import traceback
from pathlib import Path

from ..config import LOCK_PATH, LOG_DIR, STALE_RUN_MINUTES, has_llm_credentials
from ..db import connect, migrate
from ..seed import seed_defaults
from ..services import backup, discovery, extraction, fetching, interview, ranking, triage
from ..services.llm import LLMContacted, UsageTracker
from ..services.profile import ensure_profile, maybe_regenerate

APP_LOG = Path(os.environ.get("FEEDAPP_APP_LOG") or Path.home() / "Library/Logs/recommender-feed.log")


def log(msg: str) -> None:
    """Timestamped line to stdout (launchd/manual.log capture it) and to the app log.
    When stdout already IS the app log (under launchd) the file write is skipped."""
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    try:
        so, lo = os.fstat(1), APP_LOG.stat()
        if (so.st_ino, so.st_dev) == (lo.st_ino, lo.st_dev):
            return
    except OSError:
        pass
    try:
        APP_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(APP_LOG, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _expire_quests(conn) -> None:
    conn.execute(
        """UPDATE instructions SET status = 'expired', resolved_at = datetime('now')
           WHERE kind = 'quest' AND status = 'active'
             AND expires_at IS NOT NULL AND expires_at < datetime('now')"""
    )
    conn.commit()


def run_pipeline(trigger: str = "scheduled", run_id: int | None = None) -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    migrate()
    conn = connect()

    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock_file = open(LOCK_PATH, "w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("another pipeline run is in progress; exiting")
        if run_id is not None:
            conn.execute(
                """UPDATE pipeline_runs SET status='error', finished_at=datetime('now'),
                   error='another run was already in progress' WHERE id = ?""",
                (run_id,),
            )
            conn.commit()
        return 1

    # Clean up runs that died without finishing (crash / kill).
    conn.execute(
        f"""UPDATE pipeline_runs SET status='error', finished_at=datetime('now'),
            error='stale: interrupted'
            WHERE status='running' AND id != COALESCE(?, -1)
              AND started_at < datetime('now', '-{STALE_RUN_MINUTES} minutes')""",
        (run_id,),
    )
    if run_id is None:
        cur = conn.execute(
            "INSERT INTO pipeline_runs (trigger, status) VALUES (?, 'running')", (trigger,)
        )
        run_id = cur.lastrowid
    conn.commit()
    log(f"run {run_id} started (trigger={trigger})")

    seed_defaults(conn)
    ensure_profile(conn)
    _expire_quests(conn)

    usage = UsageTracker()
    stats: dict = {}
    errors: list[str] = []
    llm_ok = has_llm_credentials()
    contacted = False  # the model asked to talk to Eli: no further LLM work this run

    def set_stage(name: str) -> None:
        conn.execute("UPDATE pipeline_runs SET stage = ? WHERE id = ?", (name, run_id))
        conn.commit()
        log(f"[stage] {name}")

    def run_stage(name: str, fn) -> None:
        nonlocal contacted
        set_stage(name)
        try:
            result = fn()
            if isinstance(result, dict):
                stats[name] = result
        except LLMContacted as e:
            contacted = True
            errors.append(f"{name}: {e}")
            log(f"[contact] {e}")
            log("the model asked to talk to Eli; skipping the remaining LLM stages this run")
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: {e}")
            log(f"[error] {name}: {e}")
            traceback.print_exc()
            sys.stderr.flush()

    run_stage("fetch", lambda: fetching.fetch_all_sources(conn, usage, llm_ok))
    run_stage("extract", lambda: extraction.extract_pending(conn))
    if llm_ok:
        llm_stages = [
            ("triage", lambda: triage.triage_pending(conn, usage)),
            ("discovery", lambda: discovery.discover(conn, usage)),
            ("extract_discovered", lambda: extraction.extract_pending(conn)),
            ("triage_discovered", lambda: triage.triage_pending(conn, usage)),
            ("ranking", lambda: ranking.rank_items(conn, run_id, usage)),
            ("profile", lambda: maybe_regenerate(conn, usage)),
            ("interview", lambda: interview.maybe_ask(conn, usage)),
        ]
        for name, fn in llm_stages:
            if contacted:
                break
            run_stage(name, fn)
    else:
        errors.append(
            "no Anthropic credentials found (set ANTHROPIC_API_KEY in <data dir>/.env; see `make where`); "
            "skipped triage/discovery/ranking — feed will show chronological order"
        )
    # Always last, and always runs: snapshot + JSON export + iCloud mirror of the
    # ratings/notes dataset. See services/backup.py.
    run_stage("backup", lambda: backup.run_backup(conn))

    stats["llm"] = usage.summary()
    status = "success" if not errors else "partial"
    conn.execute(
        """UPDATE pipeline_runs SET status = ?, finished_at = datetime('now'),
           stage = 'done', stats_json = ?, error = ? WHERE id = ?""",
        (status, json.dumps(stats), "; ".join(errors) if errors else None, run_id),
    )
    conn.commit()
    conn.close()
    log(f"run {run_id} finished: {status}")
    if errors:
        log("errors:\n  " + "\n  ".join(errors))
    log(f"llm usage: {stats['llm']}")
    return 0

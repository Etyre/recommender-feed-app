"""Pipeline orchestrator. One code path for scheduled (launchd) and manual (UI) runs.
Stages: fetch -> extract -> triage -> discovery -> extract/triage (discovered) -> rank -> profile.
Per-stage failures mark the run 'partial'; later stages still run with what's available."""
from __future__ import annotations

import fcntl
import json
import traceback

from ..config import LOCK_PATH, LOG_DIR, STALE_RUN_MINUTES, has_llm_credentials
from ..db import connect, migrate
from ..seed import seed_defaults
from ..services import discovery, extraction, fetching, interview, ranking, triage
from ..services.llm import UsageTracker
from ..services.profile import ensure_profile, maybe_regenerate


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
        print("another pipeline run is in progress; exiting")
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

    seed_defaults(conn)
    ensure_profile(conn)
    _expire_quests(conn)

    usage = UsageTracker()
    stats: dict = {}
    errors: list[str] = []
    llm_ok = has_llm_credentials()

    def set_stage(name: str) -> None:
        conn.execute("UPDATE pipeline_runs SET stage = ? WHERE id = ?", (name, run_id))
        conn.commit()
        print(f"[stage] {name}")

    def run_stage(name: str, fn) -> None:
        set_stage(name)
        try:
            result = fn()
            if isinstance(result, dict):
                stats[name] = result
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: {e}")
            traceback.print_exc()

    run_stage("fetch", lambda: fetching.fetch_all_sources(conn, usage, llm_ok))
    run_stage("extract", lambda: extraction.extract_pending(conn))
    if llm_ok:
        run_stage("triage", lambda: triage.triage_pending(conn, usage))
        run_stage("discovery", lambda: discovery.discover(conn, usage))
        run_stage("extract_discovered", lambda: extraction.extract_pending(conn))
        run_stage("triage_discovered", lambda: triage.triage_pending(conn, usage))
        run_stage("ranking", lambda: ranking.rank_items(conn, run_id, usage))
        run_stage("profile", lambda: maybe_regenerate(conn, usage))
        run_stage("interview", lambda: interview.maybe_ask(conn, usage))
    else:
        errors.append(
            "no Anthropic credentials found (set ANTHROPIC_API_KEY in data/.env); "
            "skipped triage/discovery/ranking — feed will show chronological order"
        )

    stats["llm"] = usage.summary()
    status = "success" if not errors else "partial"
    conn.execute(
        """UPDATE pipeline_runs SET status = ?, finished_at = datetime('now'),
           stage = 'done', stats_json = ?, error = ? WHERE id = ?""",
        (status, json.dumps(stats), "; ".join(errors) if errors else None, run_id),
    )
    conn.commit()
    conn.close()
    print(f"run {run_id} finished: {status}")
    if errors:
        print("errors:\n  " + "\n  ".join(errors))
    print(f"llm usage: {stats['llm']}")
    return 0

import json
import sqlite3
import subprocess
import sys

from fastapi import APIRouter, Depends, HTTPException

from ..config import BACKEND_DIR, LOG_DIR, STALE_RUN_MINUTES
from .deps import get_db

router = APIRouter()


def _run_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["stats"] = json.loads(d.pop("stats_json") or "{}")
    return d


@router.post("/pipeline/run", status_code=202)
def trigger_run(conn: sqlite3.Connection = Depends(get_db)):
    running = conn.execute(
        f"""SELECT id FROM pipeline_runs WHERE status = 'running'
            AND started_at > datetime('now', '-{STALE_RUN_MINUTES} minutes')"""
    ).fetchone()
    if running:
        raise HTTPException(409, f"run {running['id']} is already in progress")
    cur = conn.execute(
        "INSERT INTO pipeline_runs (trigger, status) VALUES ('manual', 'running')"
    )
    run_id = cur.lastrowid
    conn.commit()  # the subprocess must see the row
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = open(LOG_DIR / "manual.log", "ab")
    subprocess.Popen(
        [sys.executable, "-m", "app.pipeline", "--trigger", "manual", "--run-id", str(run_id)],
        cwd=str(BACKEND_DIR),
        stdout=log,
        stderr=log,
    )
    return {"run_id": run_id}


@router.get("/usage/daily")
def usage_daily(days: int = 30, conn: sqlite3.Connection = Depends(get_db)):
    """Per-local-day LLM spend, aggregated from run stats."""
    rows = conn.execute(
        """SELECT date(started_at, 'localtime') AS day, stats_json
           FROM pipeline_runs
           WHERE stats_json IS NOT NULL AND started_at > datetime('now', ?)""",
        (f"-{min(days, 365)} days",),
    ).fetchall()
    agg: dict = {}

    def day_bucket(day: str) -> dict:
        return agg.setdefault(
            day, {"day": day, "runs": 0, "cost_usd": 0.0,
                  "input_tokens": 0, "output_tokens": 0}
        )

    for row in rows:
        llm = (json.loads(row["stats_json"]) or {}).get("llm") or {}
        d = day_bucket(row["day"])
        d["runs"] += 1
        d["cost_usd"] += llm.get("est_cost_usd", 0) or 0
        d["input_tokens"] += llm.get("input_tokens", 0) or 0
        d["output_tokens"] += llm.get("output_tokens", 0) or 0
    # Non-pipeline spend (chat turns etc.)
    for row in conn.execute(
        """SELECT date(created_at, 'localtime') AS day, input_tokens, output_tokens, est_cost_usd
           FROM llm_usage_log WHERE created_at > datetime('now', ?)""",
        (f"-{min(days, 365)} days",),
    ):
        d = day_bucket(row["day"])
        d["cost_usd"] += row["est_cost_usd"]
        d["input_tokens"] += row["input_tokens"]
        d["output_tokens"] += row["output_tokens"]
    out = sorted(agg.values(), key=lambda x: x["day"], reverse=True)
    for d in out:
        d["cost_usd"] = round(d["cost_usd"], 4)
    return out


@router.get("/pipeline/runs")
def list_runs(limit: int = 10, conn: sqlite3.Connection = Depends(get_db)):
    rows = conn.execute(
        "SELECT * FROM pipeline_runs ORDER BY id DESC LIMIT ?", (min(limit, 100),)
    ).fetchall()
    return [_run_dict(r) for r in rows]


@router.get("/pipeline/runs/{run_id}")
def get_run(run_id: int, conn: sqlite3.Connection = Depends(get_db)):
    row = conn.execute("SELECT * FROM pipeline_runs WHERE id = ?", (run_id,)).fetchone()
    if not row:
        raise HTTPException(404, "run not found")
    return _run_dict(row)

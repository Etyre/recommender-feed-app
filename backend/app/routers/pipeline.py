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

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ..config import QUEST_DEFAULT_DAYS
from ..schemas import InstructionIn, InstructionPatch
from .deps import get_db

router = APIRouter()


@router.get("/instructions")
def list_instructions(conn: sqlite3.Connection = Depends(get_db)):
    rows = conn.execute(
        "SELECT * FROM instructions WHERE status != 'archived' ORDER BY id DESC"
    ).fetchall()
    return [dict(r) for r in rows]


@router.post("/instructions", status_code=201)
def add_instruction(body: InstructionIn, conn: sqlite3.Connection = Depends(get_db)):
    if body.kind not in ("quest", "standing"):
        raise HTTPException(400, "kind must be 'quest' or 'standing'")
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "text is required")
    expires = (
        f"datetime('now', '+{QUEST_DEFAULT_DAYS} days')" if body.kind == "quest" else "NULL"
    )
    cur = conn.execute(
        f"INSERT INTO instructions (text, kind, expires_at) VALUES (?, ?, {expires})",
        (text, body.kind),
    )
    row = conn.execute(
        "SELECT * FROM instructions WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    return dict(row)


@router.patch("/instructions/{instruction_id}")
def patch_instruction(
    instruction_id: int, body: InstructionPatch, conn: sqlite3.Connection = Depends(get_db)
):
    row = conn.execute(
        "SELECT * FROM instructions WHERE id = ?", (instruction_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "instruction not found")
    if body.status is not None:
        if body.status not in ("active", "satisfied", "expired", "archived"):
            raise HTTPException(400, "invalid status")
        resolved = "datetime('now')" if body.status != "active" else "NULL"
        conn.execute(
            f"UPDATE instructions SET status = ?, resolved_at = {resolved} WHERE id = ?",
            (body.status, instruction_id),
        )
    if body.text is not None:
        conn.execute(
            "UPDATE instructions SET text = ? WHERE id = ?",
            (body.text.strip(), instruction_id),
        )
    row = conn.execute(
        "SELECT * FROM instructions WHERE id = ?", (instruction_id,)
    ).fetchone()
    return dict(row)

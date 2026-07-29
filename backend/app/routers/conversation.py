import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ..config import QUEST_DEFAULT_DAYS, has_llm_credentials
from ..schemas import ChatIn
from ..services import interview
from ..services.llm import UsageTracker
from .deps import get_db

router = APIRouter()


@router.get("/conversation")
def get_conversation(conn: sqlite3.Connection = Depends(get_db)):
    return interview.all_messages(conn)


@router.post("/conversation/proposals/{message_id}/{index}/accept")
def accept_proposal(
    message_id: int, index: int, conn: sqlite3.Connection = Depends(get_db)
):
    """Turn an agent-proposed instruction into a real one, and remember that it
    was accepted (so the chip stays checked across reloads)."""
    row = conn.execute(
        "SELECT proposals_json FROM conversation_messages WHERE id = ? AND role = 'agent'",
        (message_id,),
    ).fetchone()
    if not row or not row["proposals_json"]:
        raise HTTPException(404, "no proposals on that message")
    proposals = json.loads(row["proposals_json"])
    if not 0 <= index < len(proposals):
        raise HTTPException(404, "no such proposal")
    proposal = proposals[index]
    if not proposal.get("added"):
        kind = proposal.get("kind") if proposal.get("kind") in ("quest", "standing") else "standing"
        expires = (
            f"datetime('now', '+{QUEST_DEFAULT_DAYS} days')" if kind == "quest" else "NULL"
        )
        conn.execute(
            f"INSERT INTO instructions (text, kind, expires_at) VALUES (?, ?, {expires})",
            (proposal["text"], kind),
        )
        proposal["added"] = True
        conn.execute(
            "UPDATE conversation_messages SET proposals_json = ? WHERE id = ?",
            (json.dumps(proposals), message_id),
        )
    return interview.all_messages(conn)


@router.post("/conversation")
def send_message(body: ChatIn, conn: sqlite3.Connection = Depends(get_db)):
    if not has_llm_credentials():
        raise HTTPException(400, "no Anthropic credentials configured (data/.env)")
    usage = UsageTracker()
    message = body.message.strip() if body.message else None
    try:
        interview.converse(conn, message or None, usage)
    finally:
        summary = usage.summary()
        if summary["calls"]:
            conn.execute(
                """INSERT INTO llm_usage_log (context, input_tokens, output_tokens, est_cost_usd)
                   VALUES ('chat', ?, ?, ?)""",
                (summary["input_tokens"], summary["output_tokens"], summary["est_cost_usd"]),
            )
            conn.commit()
    return interview.all_messages(conn)

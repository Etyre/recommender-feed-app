import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ..config import has_llm_credentials
from ..schemas import ChatIn
from ..services import interview
from ..services.llm import UsageTracker
from .deps import get_db

router = APIRouter()


@router.get("/conversation")
def get_conversation(conn: sqlite3.Connection = Depends(get_db)):
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

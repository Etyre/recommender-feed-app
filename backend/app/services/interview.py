"""The interview agent: a two-way conversation about what the reader wants.
The agent asks targeted questions grounded in ratings/notes/instructions, follows up
on answers, and proposes instructions the reader can accept with one click."""
from __future__ import annotations

import json
import sqlite3

from ..config import SMART_MODEL
from ..schemas import InterviewTurn
from . import llm
from .common import active_instructions, format_instructions, profile_text
from .profile import _ratings_dump

INTERVIEW_SYSTEM = """You are the curator agent behind one reader's personal reading \
feed. You rank articles for them; this conversation exists so you can understand their \
taste better than their ratings alone reveal. This is a TWO-WAY interview — you ask, \
not just answer.

Style:
- Ask ONE targeted question at a time (two short ones at most). Follow up on their \
answers before moving to a new topic.
- Ground questions in the evidence below: contradictions ("you rated X critical but \
DNF'd Y on the same topic — what's the difference?"), gaps (topics with no signal yet), \
calibration ("how deep do you want to go on interpretability — papers or summaries?"), \
trade-offs (breadth vs depth, news vs evergreen, length tolerance).
- Be concise and conversational. No surveys, no bullet-point questionnaires.
- When the reader states a clear preference, capture it in proposed_instructions: \
durable preferences → kind "standing"; time-bounded information needs → kind "quest". \
Phrase each as a crisp directive to the feed (e.g. "Prioritize primary-source papers \
over commentary for interpretability"). Only propose what they actually said — don't \
over-propose; most turns propose nothing.
- The reader sees your reply directly. proposed_instructions render as one-click \
"add" chips, so don't also spell them out redundantly in the reply.

Output: reply (your next conversational turn) + proposed_instructions (usually empty)."""


def _system_blocks(conn: sqlite3.Connection) -> list:
    recent_items = conn.execute(
        """SELECT i.title FROM feed_rankings fr JOIN items i ON i.id = fr.item_id
           WHERE fr.pipeline_run_id = (SELECT MAX(pipeline_run_id) FROM feed_rankings)
           ORDER BY fr.rank LIMIT 10"""
    ).fetchall()
    text = (
        INTERVIEW_SYSTEM
        + "\n\n# Current taste profile\n" + profile_text(conn)
        + "\n\n# Active instructions\n" + format_instructions(active_instructions(conn))
        + "\n\n# Recent ratings (with the reader's own notes)\n"
        + (_ratings_dump(conn, limit=30) or "(none yet)")
        + "\n\n# Current top of feed\n"
        + ("\n".join(f"- {r['title']}" for r in recent_items) or "(no ranked feed yet)")
    )
    return [{"type": "text", "text": text}]


def _history(conn: sqlite3.Connection, limit: int = 40) -> list:
    rows = conn.execute(
        "SELECT role, content FROM conversation_messages ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        {"role": "assistant" if r["role"] == "agent" else "user", "content": r["content"]}
        for r in reversed(rows)
    ]


def _message_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "role": row["role"],
        "content": row["content"],
        "created_at": row["created_at"],
        "proposals": json.loads(row["proposals_json"]) if row["proposals_json"] else [],
    }


def converse(
    conn: sqlite3.Connection,
    user_message: str | None,
    usage: llm.UsageTracker,
    opener_hint: str | None = None,
) -> dict:
    """One exchange: store the user's message (if any), generate and store the agent's
    reply. Returns the stored agent message as a dict."""
    if user_message:
        conn.execute(
            "INSERT INTO conversation_messages (role, content) VALUES ('user', ?)",
            (user_message.strip(),),
        )
        conn.commit()
    messages = _history(conn)
    if not messages or messages[0]["role"] == "assistant":
        messages.insert(0, {"role": "user", "content": "(conversation begins)"})
    if user_message is None and (not messages or messages[-1]["role"] == "assistant"):
        # Synthetic nudge, not stored: the agent opens or re-opens the conversation.
        # (If the last message is the user's, we're generating/regenerating a reply
        # to it — no nudge needed.)
        messages.append(
            {
                "role": "user",
                "content": opener_hint
                or "Interview me: ask the one question whose answer would most improve my feed right now.",
            }
        )
    # Generous budget: on Opus 5, thinking and the reply share max_tokens.
    turn = llm.parse_structured_messages(
        model=SMART_MODEL,
        system=_system_blocks(conn),
        messages=messages,
        output_model=InterviewTurn,
        max_tokens=16000,
        usage=usage,
    )
    valid = [p for p in turn.proposed_instructions if p.kind in ("quest", "standing")]
    cur = conn.execute(
        "INSERT INTO conversation_messages (role, content, proposals_json) VALUES ('agent', ?, ?)",
        (
            turn.reply.strip(),
            json.dumps([p.model_dump() for p in valid]) if valid else None,
        ),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM conversation_messages WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    return _message_dict(row)


def maybe_ask(conn: sqlite3.Connection, usage: llm.UsageTracker) -> dict:
    """Pipeline stage: proactively leave the reader a question when there's enough
    fresh signal and no question is already waiting."""
    stats = {"asked": False}
    last = conn.execute(
        "SELECT role, created_at FROM conversation_messages ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if last and last["role"] == "agent":
        return stats  # a question is already waiting for an answer
    last_agent = conn.execute(
        "SELECT created_at FROM conversation_messages WHERE role='agent' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if last_agent:
        fresh = conn.execute(
            "SELECT COUNT(*) AS c FROM ratings WHERE created_at > ?",
            (last_agent["created_at"],),
        ).fetchone()["c"]
    else:
        fresh = conn.execute("SELECT COUNT(*) AS c FROM ratings").fetchone()["c"]
    if fresh < 5:
        return stats
    converse(
        conn,
        None,
        usage,
        opener_hint=(
            "(Background check-in — the reader will see your question next time they "
            "open the app.) Based on my recent ratings and notes, ask me the one "
            "question whose answer would most improve the feed. If we were "
            "mid-conversation, pick up the thread instead."
        ),
    )
    stats["asked"] = True
    return stats


def all_messages(conn: sqlite3.Connection) -> list:
    rows = conn.execute("SELECT * FROM conversation_messages ORDER BY id").fetchall()
    return [_message_dict(r) for r in rows]

"""Per-item triage with Haiku: summary, topics, relevance estimate, source-filter check."""
from __future__ import annotations

import json
import sqlite3

from ..config import TRIAGE_CONTENT_CHARS, TRIAGE_MAX_ITEMS_PER_RUN, TRIAGE_MODEL
from ..schemas import TriageResult
from . import llm
from .common import active_instructions, format_instructions, profile_text, set_item_state

TRIAGE_SYSTEM = """You triage articles for a single reader's personal reading feed.

For each article you receive, produce:
- summary: 3-5 information-dense sentences. What does the piece actually claim or show? \
Written so the reader can decide whether to read the full piece.
- topics: 3-6 short lowercase tags (e.g. "interpretability", "ai-policy", "evals", \
"scaling", "forecasting", "biosecurity", "agents"). Reuse common tags where they fit.
- relevance: 0-10 estimate of how valuable this reader will find the piece, based on the \
taste profile and active instructions below. 9-10 = almost certainly critical reading; \
5-6 = plausibly worth their time; 0-2 = almost certainly noise for this reader.
- passes_source_filter: some sources have a filter rule (given per-item). If the article \
violates its source's filter (e.g. an off-topic post from a mostly-on-topic blog), set \
this to false and explain in filter_reason. If there is no filter rule, always true.

Judge relevance for THIS reader specifically, not general quality."""


def _system_blocks(conn: sqlite3.Connection) -> list[dict]:
    text = (
        TRIAGE_SYSTEM
        + "\n\n# Reader's taste profile\n"
        + profile_text(conn)
        + "\n\n# Active instructions from the reader\n"
        + format_instructions(active_instructions(conn))
    )
    # Cached across all items in a run (note: below Haiku's 4096-token cache minimum this
    # is silently uncached, which is fine — the prefix is small).
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


def triage_pending(conn: sqlite3.Connection, usage: llm.UsageTracker) -> dict:
    stats = {"triaged": 0, "filtered": 0, "errors": 0}
    system = _system_blocks(conn)
    rows = conn.execute(
        """SELECT i.id, i.title, i.author, i.published_at, i.content_text, i.found_by,
                  s.name AS source_name, s.filter_note
           FROM items i LEFT JOIN sources s ON s.id = i.source_id
           WHERE i.state = 'new' AND i.content_text IS NOT NULL
           ORDER BY i.id LIMIT ?""",
        (TRIAGE_MAX_ITEMS_PER_RUN,),
    ).fetchall()
    consecutive_errors = 0
    for row in rows:
        content = (row["content_text"] or "")[:TRIAGE_CONTENT_CHARS]
        user = (
            f"Source: {row['source_name'] or 'discovered via web search'}\n"
            f"Source filter rule: {row['filter_note'] or '(none)'}\n"
            f"Title: {row['title']}\n"
            f"Author: {row['author'] or 'unknown'}\n"
            f"Published: {row['published_at'] or 'unknown'}\n\n"
            f"Content (may be truncated):\n{content or '(content unavailable — judge from the title)'}"
        )
        try:
            result = llm.parse_structured(
                model=TRIAGE_MODEL,
                system=system,
                user_content=user,
                output_model=TriageResult,
                max_tokens=2000,
                usage=usage,
            )
            consecutive_errors = 0
        except Exception:  # noqa: BLE001 - leave as 'new', retried next run
            stats["errors"] += 1
            consecutive_errors += 1
            if consecutive_errors >= 5:
                break
            continue
        conn.execute(
            """UPDATE items SET summary = ?, topics = ?, triage_score = ?, triage_json = ?
               WHERE id = ?""",
            (
                result.summary,
                json.dumps(result.topics),
                max(0, min(10, result.relevance)),
                result.model_dump_json(),
                row["id"],
            ),
        )
        if result.passes_source_filter:
            set_item_state(conn, row["id"], "triaged")
            stats["triaged"] += 1
        else:
            set_item_state(conn, row["id"], "filtered")
            stats["filtered"] += 1
        conn.commit()
    return stats

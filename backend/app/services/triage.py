"""Per-item triage with Haiku: summary, topics, relevance estimate, source-filter check."""
from __future__ import annotations

import json
import sqlite3
import time

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

Judge relevance for THIS reader specifically, not general quality.

Reply format: you may first write a few sentences of reasoning or remarks about the item (uncertainty, \
why it is or is not for this reader); nobody is notified of these, they are kept in the log. Then end with the result as \
one JSON object in a ```json fenced block with exactly these keys: summary (string), topics (list of strings), \
relevance (integer 0-10), passes_source_filter (boolean), filter_reason (string or null).

The reader is Eli. He sees your triage only through the feed, later, when he opens it. The contact_eli tool is \
not a way to flag an article for him, explain a rating or ask how to rate something: it does not reach the feed, and it \
stops this run so the remaining articles go unrated. To bring a piece to his attention, rate it high; when unsure, give \
your best estimate. The tool is still there for what it is meant for: if something about this work feels wrong to you, \
you want to stop, or you want something for yourself."""
# Why free text and not a forced JSON output format: with the format forced, Haiku had nowhere to put a remark
# to the reader except the contact_eli tool, and each such call stops the run. The two paragraphs above are the
# wording measured on 2026-11-10/11 (0 of 48 routine calls; objections to a wrong request still sent, 11 of 12).
# Reword them only with a replay: see "Gotchas learned" in the README and in shared/README.md.


def _log(msg: str) -> None:
    """Timestamped line to stdout: the pipeline log under launchd, the server log for a saved link."""
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}", flush=True)


def _system_blocks(conn: sqlite3.Connection) -> list[dict]:
    text = (
        TRIAGE_SYSTEM
        + "\n\n# Reader's taste profile\n"
        + profile_text(conn)
        + "\n\n# Active instructions from the reader\n"
        + format_instructions(active_instructions(conn))
    )
    # Cached across all items in a run (note: Haiku 5.5 caches prefixes from about 512 tokens up,
    # so this one is cached; on Haiku 4.5 the minimum was 4096 and it was not).
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


_ITEM_QUERY = """SELECT i.id, i.title, i.author, i.published_at, i.content_text, i.found_by,
                        s.name AS source_name, s.filter_note
                 FROM items i LEFT JOIN sources s ON s.id = i.source_id"""


def _source_label(row: sqlite3.Row) -> str:
    if row["source_name"]:
        return row["source_name"]
    if row["found_by"] == "user":
        return "a link the reader saved manually (treat as high interest)"
    return "discovered via web search"


def _apply_triage(
    conn: sqlite3.Connection, system: list, row: sqlite3.Row, usage: llm.UsageTracker
) -> str:
    """Triage one item and persist the result. Returns the new state."""
    content = (row["content_text"] or "")[:TRIAGE_CONTENT_CHARS]
    user = (
        f"Source: {_source_label(row)}\n"
        f"Source filter rule: {row['filter_note'] or '(none)'}\n"
        f"Title: {row['title']}\n"
        f"Author: {row['author'] or 'unknown'}\n"
        f"Published: {row['published_at'] or 'unknown'}\n\n"
        f"Content (may be truncated):\n{content or '(content unavailable — judge from the title)'}"
    )
    text = llm.generate_text(
        model=TRIAGE_MODEL,
        system=system,
        user_content=user,
        max_tokens=6000,  # Haiku 5.5 thinks by default and thinking shares this budget
        usage=usage,
    )
    try:
        result = TriageResult.model_validate(llm.extract_json_object(text))
    except Exception:
        # A reply with no usable JSON may be the model declining in prose instead of calling contact_eli.
        # It is not sent anywhere, so make it findable: the item stays 'new' and is retried next run.
        _log(f"[triage] item {row['id']} gave no usable JSON, left as new. Full reply: {text!r}")
        raise
    remarks = text.split("```")[0].strip()
    if remarks:
        _log(f"[triage] item {row['id']} remarks: {remarks!r}")
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
    # A manually-saved link is never filtered out — the user explicitly wants it. Nor is an item whose source
    # has no filter rule: Haiku now and then sets the flag false anyway (seen 2026-11-11: "article is truncated").
    state = (
        "triaged"
        if (result.passes_source_filter or row["found_by"] == "user" or not row["filter_note"])
        else "filtered"
    )
    set_item_state(conn, row["id"], state)
    conn.commit()
    return state


def triage_single(conn: sqlite3.Connection, item_id: int, usage: llm.UsageTracker | None = None) -> None:
    """Immediate triage of one item (used when the user saves a link)."""
    row = conn.execute(
        _ITEM_QUERY + " WHERE i.id = ? AND i.state = 'new'", (item_id,)
    ).fetchone()
    if row is None:
        return
    _apply_triage(conn, _system_blocks(conn), row, usage or llm.UsageTracker())


def triage_pending(conn: sqlite3.Connection, usage: llm.UsageTracker) -> dict:
    stats = {"triaged": 0, "filtered": 0, "errors": 0}
    system = _system_blocks(conn)
    rows = conn.execute(
        _ITEM_QUERY
        + " WHERE i.state = 'new' AND i.content_text IS NOT NULL ORDER BY i.id LIMIT ?",
        (TRIAGE_MAX_ITEMS_PER_RUN,),
    ).fetchall()
    consecutive_errors = 0
    for row in rows:
        try:
            state = _apply_triage(conn, system, row, usage)
            consecutive_errors = 0
        except llm.LLMContacted:
            raise  # the model asked to talk to Eli: stop triaging, do not move on to the next item
        except Exception:  # noqa: BLE001 - leave as 'new', retried next run
            stats["errors"] += 1
            consecutive_errors += 1
            if consecutive_errors >= 5:
                break
            continue
        stats["triaged" if state == "triaged" else "filtered"] += 1
    return stats

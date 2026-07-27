"""Marginal-value ranking with Opus: the core mechanic of the feed."""
from __future__ import annotations

import json
import sqlite3

from ..config import (
    AUTO_DISMISS_DAYS,
    AUTO_DISMISS_MAX_TRIAGE,
    RANKING_MAX_CANDIDATES,
    SMART_MODEL,
)
from ..schemas import RankingResult
from . import llm
from .common import active_instructions, format_instructions, profile_text

RANKING_SYSTEM = """You produce the ranked reading feed for one specific reader. You will \
receive their taste profile, their active instructions, the previous feed's top ranking, \
and a set of candidate items (with summaries). Order the candidates by expected value to \
this reader.

Rating semantics you are optimizing for — after reading, the reader rates items:
- "critical": absolutely critical to have read
- "worth_it": worth their time to find and read
- "fine": fine, but they wouldn't have missed much
- "not_worth": not worth reading
Your goal is that high ranks earn "critical"/"worth_it" and low ranks would have earned \
"fine"/"not_worth".

MARGINAL VALUE — the key rule: build the list greedily. For each position, choose the item \
with the highest expected value GIVEN EVERYTHING RANKED ABOVE IT. If an item substantially \
overlaps something already placed (same paper, same news event, same argument), discount it \
and set redundant_with_item_id to the higher-ranked item's id. A second solid article on a \
topic already covered at rank 3 should generally fall below a decent article on an \
uncovered topic the reader cares about.

Other rules:
- Items marked "saved manually by the reader" are the strongest possible interest \
signal: rank them at or near the top until read, above comparable source items.
- Short-term quests are high priority: items answering an active quest rank near the top.
- Recency matters more for news-like items than for evergreen papers and essays.
- STABILITY: the previous ranking is provided. Keep ordering roughly stable unless new \
items or new information justify movement — the reader finds constant reshuffling \
disorienting.
- rationale: one sentence, written to the reader, saying why the item is at this position \
for them specifically (mention overlap when discounted).
- Include every candidate item exactly once, ordered from rank 1 (best) downward. Use each \
item's numeric id exactly as given."""


def auto_dismiss_stale(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        """UPDATE items SET state = 'dismissed', state_changed_at = datetime('now')
           WHERE state IN ('triaged','shown')
             AND COALESCE(triage_score, 10) <= ?
             AND COALESCE(published_at, discovered_at) < datetime('now', ?)""",
        (AUTO_DISMISS_MAX_TRIAGE, f"-{AUTO_DISMISS_DAYS} days"),
    )
    return cur.rowcount


def _candidates(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT i.id, i.title, i.published_at, i.discovered_at, i.topics, i.triage_score,
                  i.summary, i.found_by, s.name AS source_name
           FROM items i LEFT JOIN sources s ON s.id = i.source_id
           WHERE i.state IN ('triaged','shown')
           ORDER BY COALESCE(i.triage_score, 5) DESC,
                    COALESCE(i.published_at, i.discovered_at) DESC
           LIMIT ?""",
        (RANKING_MAX_CANDIDATES,),
    ).fetchall()


def _card(row: sqlite3.Row) -> str:
    topics = ", ".join(json.loads(row["topics"])) if row["topics"] else ""
    via = ""
    if row["found_by"] == "discovery":
        via = " (found via web discovery)"
    elif row["found_by"] == "user":
        via = " (saved manually by the reader)"
    return (
        f"[id={row['id']}] {row['title']}\n"
        f"  source: {row['source_name'] or 'web'}{via} | published: "
        f"{row['published_at'] or 'unknown'} | topics: {topics} | "
        f"triage relevance: {row['triage_score']}\n"
        f"  summary: {row['summary'] or '(none)'}"
    )


def _previous_top(conn: sqlite3.Connection, n: int = 20) -> str:
    row = conn.execute(
        "SELECT pipeline_run_id FROM feed_rankings ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not row:
        return "(no previous ranking — this is the first ranked run)"
    rows = conn.execute(
        """SELECT fr.rank, fr.item_id, i.title FROM feed_rankings fr
           JOIN items i ON i.id = fr.item_id
           WHERE fr.pipeline_run_id = ? ORDER BY fr.rank LIMIT ?""",
        (row["pipeline_run_id"], n),
    ).fetchall()
    return "\n".join(f"{r['rank']}. [id={r['item_id']}] {r['title']}" for r in rows)


def rank_items(
    conn: sqlite3.Connection, run_id: int, usage: llm.UsageTracker
) -> dict:
    dismissed = auto_dismiss_stale(conn)
    conn.commit()
    candidates = _candidates(conn)
    stats = {"candidates": len(candidates), "auto_dismissed": dismissed, "ranked": 0}
    if not candidates:
        return stats
    candidate_ids = {r["id"] for r in candidates}
    user = (
        "# Reader's taste profile\n" + profile_text(conn)
        + "\n\n# Active instructions\n" + format_instructions(active_instructions(conn))
        + "\n\n# Previous feed top ranking (for stability)\n" + _previous_top(conn)
        + "\n\n# Candidate items\n" + "\n\n".join(_card(r) for r in candidates)
    )
    result = llm.parse_structured(
        model=SMART_MODEL,
        system=RANKING_SYSTEM,
        user_content=user,
        output_model=RankingResult,
        max_tokens=16000,
        usage=usage,
    )
    seen: set[int] = set()
    rank = 0
    rows_to_insert: list[tuple] = []
    for entry in result.rankings:
        if entry.item_id not in candidate_ids or entry.item_id in seen:
            continue  # drop hallucinated / duplicated ids
        rank += 1
        seen.add(entry.item_id)
        redundant = (
            entry.redundant_with_item_id
            if entry.redundant_with_item_id in candidate_ids
            else None
        )
        rows_to_insert.append(
            (run_id, entry.item_id, rank, entry.score, entry.rationale.strip(), redundant)
        )
    for row in candidates:  # anything the model omitted goes at the bottom
        if row["id"] not in seen:
            rank += 1
            seen.add(row["id"])
            rows_to_insert.append(
                (run_id, row["id"], rank, 0.0, "Not ranked by the model this run.", None)
            )
    conn.executemany(
        """INSERT INTO feed_rankings
           (pipeline_run_id, item_id, rank, score, rationale, redundant_with_item_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        rows_to_insert,
    )
    conn.execute(
        f"""UPDATE items SET state = 'shown', state_changed_at = datetime('now')
            WHERE state = 'triaged' AND id IN ({','.join('?' * len(seen))})""",
        list(seen),
    )
    conn.commit()
    stats["ranked"] = rank
    return stats

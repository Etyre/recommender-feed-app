"""Discovery agent: Opus + server-side web search. Finds one-off items for active quests
and interests, and proposes new permanent sources (which the user must approve)."""
from __future__ import annotations

import json
import sqlite3
from urllib.parse import urlsplit

from ..config import (
    DISCOVERY_MAX_ITEMS,
    DISCOVERY_MAX_SEARCHES,
    DISCOVERY_WITHOUT_QUESTS,
    MAX_PENDING_PROPOSALS,
    SMART_MODEL,
)
from ..schemas import DiscoveryResult
from . import llm
from .common import active_instructions, format_instructions, profile_text
from .fetching import insert_item

DISCOVERY_SYSTEM = """You are the discovery agent for one reader's personal reading feed. \
The feed already fetches from a set of registered sources; your job is to find valuable \
content the registered sources DON'T cover, using web search.

Priorities:
1. Active short-term quests are your top priority — find items that directly serve them.
2. Standing preferences and the taste profile guide broader discovery.
3. Include at most one "wildcard" item per run: outside current stated interests but \
plausibly valuable to this reader (this keeps the feed from narrowing over time).

Rules:
- Never return items from the registered source domains (the fetcher already covers them) \
or items matching recently-seen titles.
- Prefer primary sources (the paper, the post) over aggregator coverage.
- If you repeatedly find good content from one place, propose it as a permanent source — \
but never propose previously-rejected URLs, and don't propose when the pending queue is full.
- For each active quest, judge whether it now seems satisfied and say so in quest_updates \
(suggestion: "likely_satisfied" or "keep_looking") — the reader decides, you only suggest.

When you are done searching, output your final answer as a single JSON object in a \
```json fence, with exactly this shape:
{
  "found_items": [{"url": str, "title": str, "why_relevant": str, "for_instruction_id": int|null}],
  "source_proposals": [{"url": str, "name": str, "rationale": str, "feed_url": str|null, "sample_item_urls": [str]}],
  "quest_updates": [{"instruction_id": int, "suggestion": str, "note": str}]
}
Empty lists are fine. No other text after the JSON block."""


def discover(conn: sqlite3.Connection, usage: llm.UsageTracker) -> dict:
    stats = {"skipped": False, "found_items": 0, "proposals": 0, "quest_updates": 0}
    instructions = active_instructions(conn)
    quests = [r for r in instructions if r["kind"] == "quest"]
    if not quests and not DISCOVERY_WITHOUT_QUESTS:
        stats["skipped"] = True
        return stats

    source_domains = sorted(
        {
            urlsplit(r["url"]).netloc
            for r in conn.execute("SELECT url FROM sources WHERE status = 'active'")
        }
    )
    recent_titles = [
        r["title"]
        for r in conn.execute(
            "SELECT title FROM items ORDER BY id DESC LIMIT 40"
        )
    ]
    rejected = [
        r["url"]
        for r in conn.execute(
            "SELECT url FROM source_proposals WHERE status = 'rejected'"
        )
    ]
    pending_count = conn.execute(
        "SELECT COUNT(*) AS c FROM source_proposals WHERE status = 'pending'"
    ).fetchone()["c"]

    user = (
        "# Active instructions\n" + format_instructions(instructions)
        + "\n\n# Taste profile\n" + profile_text(conn)
        + "\n\n# Registered source domains (do NOT return items from these)\n"
        + ("\n".join(f"- {d}" for d in source_domains) or "(none)")
        + "\n\n# Recently seen titles (do NOT re-find these)\n"
        + "\n".join(f"- {t}" for t in recent_titles)
        + "\n\n# Previously rejected source proposals (never re-propose)\n"
        + ("\n".join(f"- {u}" for u in rejected) or "(none)")
        + f"\n\n# Proposal queue\n{pending_count} of {MAX_PENDING_PROPOSALS} pending slots used."
        + f"\n\nFind up to {DISCOVERY_MAX_ITEMS} items now."
    )
    text = llm.run_with_web_search(
        model=SMART_MODEL,
        system=DISCOVERY_SYSTEM,
        user_content=user,
        max_uses=DISCOVERY_MAX_SEARCHES,
        usage=usage,
    )
    result = DiscoveryResult.model_validate(llm.extract_json_object(text))

    for item in result.found_items[:DISCOVERY_MAX_ITEMS]:
        instruction_id = item.for_instruction_id
        if instruction_id is not None and not any(
            r["id"] == instruction_id for r in instructions
        ):
            instruction_id = None
        item_id = insert_item(
            conn,
            url=item.url,
            title=item.title,
            found_by="discovery",
            discovery_instruction_id=instruction_id,
        )
        if item_id:
            stats["found_items"] += 1

    slots = MAX_PENDING_PROPOSALS - pending_count
    for proposal in result.source_proposals[: max(0, slots)]:
        if proposal.url in rejected:
            continue
        cur = conn.execute(
            """INSERT OR IGNORE INTO source_proposals
               (name, url, feed_url, rationale, sample_item_urls)
               VALUES (?, ?, ?, ?, ?)""",
            (
                proposal.name,
                proposal.url,
                proposal.feed_url,
                proposal.rationale,
                json.dumps(proposal.sample_item_urls),
            ),
        )
        if cur.rowcount:
            stats["proposals"] += 1

    for update in result.quest_updates:
        cur = conn.execute(
            """UPDATE instructions SET agent_status_note = ?
               WHERE id = ? AND status = 'active'""",
            (f"{update.suggestion}: {update.note}"[:500], update.instruction_id),
        )
        if cur.rowcount:
            stats["quest_updates"] += 1

    conn.commit()
    return stats

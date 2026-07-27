"""Taste profile: a periodically-regenerated distillation of ratings + notes.
This document (not raw history) is what triage/ranking/discovery prompts consume,
so their prompt size stays flat as history grows."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from ..config import (
    PROFILE_REGEN_MAX_AGE_DAYS,
    PROFILE_REGEN_MIN_NEW_RATINGS,
    SMART_MODEL,
)
from . import llm
from .common import get_latest_profile

STARTER_PROFILE = """# Taste profile (starter — will be regenerated from ratings)

## Strong interests
- Frontier AI lab research and announcements (Anthropic — papers and blog posts).
- AI evaluations and dangerous-capability testing (METR).
- AI existential risk, strategy, and macrostrategy (Forethought, AI Futures Project).
- High-signal AI commentary and weekly synthesis (Zvi Mowshowitz).
- AI policy and governance developments that matter for the trajectory of the field.

## Anti-interests / fatigue
- (none recorded yet)

## Redundancy sensitivities
- One good treatment of a news event is enough; prefer the primary source.

## Calibration examples
- (none yet — will be filled in from actual ratings and notes)
"""

PROFILE_SYSTEM = """You maintain the taste profile document for one reader's personal \
reading feed. The profile is consumed by other models to triage and rank articles, so it \
must be concrete, evidence-based, and information-dense (~800-1500 tokens max).

Rewrite the profile from the previous version plus the reader's ratings and notes. \
Rating scale: critical (absolutely must have read) > worth_it (worth their time) > fine \
(wouldn't have missed much) > not_worth (waste of time). There is also "didnt_finish" \
(opened but abandoned partway) — treat it as evidence the piece failed to hold their \
attention (length, style, or fading interest in the topic) unless the note says \
otherwise. The notes are the reader's own words about WHY something was or wasn't \
valuable — weight them heavily and quote them.

Output ONLY the markdown document, with exactly these sections:
# Taste profile
## Strong interests        (with evidence: 'rated X critical because ...')
## Anti-interests / fatigue (topics the reader is tired of or rates poorly)
## Redundancy sensitivities (topics where one good item suffices)
## Calibration examples     (2-3 'rated critical' and 2-3 'rated not_worth' items, with \
the reader's notes verbatim where available)

Do not invent preferences that the evidence doesn't support. Keep clearly-still-relevant \
material from the previous profile even if recent ratings don't re-confirm it."""


def ensure_profile(conn: sqlite3.Connection) -> None:
    if get_latest_profile(conn) is None:
        conn.execute(
            "INSERT INTO taste_profiles (content_md, ratings_count_at_generation) VALUES (?, 0)",
            (STARTER_PROFILE,),
        )
        conn.commit()


def _ratings_dump(conn: sqlite3.Connection, limit: int = 200) -> str:
    rows = conn.execute(
        """SELECT r.rating, r.note, r.created_at, i.title, s.name AS source_name
           FROM ratings r
           JOIN items i ON i.id = r.item_id
           LEFT JOIN sources s ON s.id = i.source_id
           WHERE r.id IN (SELECT MAX(id) FROM ratings GROUP BY item_id)
           ORDER BY r.id DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    lines = []
    for r in rows:
        note = f' — reader\'s note: "{r["note"]}"' if r["note"] else ""
        lines.append(
            f"- [{r['rating']}] {r['title']} ({r['source_name'] or 'discovered'}){note}"
        )
    return "\n".join(lines)


def maybe_regenerate(conn: sqlite3.Connection, usage: llm.UsageTracker) -> dict:
    stats = {"regenerated": False}
    latest = get_latest_profile(conn)
    if latest is None:
        ensure_profile(conn)
        return stats
    total_ratings = conn.execute("SELECT COUNT(*) AS c FROM ratings").fetchone()["c"]
    new_since = total_ratings - latest["ratings_count_at_generation"]
    generated_at = datetime.fromisoformat(latest["generated_at"])
    age = datetime.utcnow() - generated_at
    due = new_since >= PROFILE_REGEN_MIN_NEW_RATINGS or (
        age > timedelta(days=PROFILE_REGEN_MAX_AGE_DAYS) and new_since > 0
    )
    if not due:
        return stats
    user = (
        "# Previous profile\n" + latest["content_md"]
        + "\n\n# Ratings (most recent first; current rating per item)\n"
        + (_ratings_dump(conn) or "(none)")
    )
    content = llm.generate_text(
        model=SMART_MODEL,
        system=PROFILE_SYSTEM,
        user_content=user,
        max_tokens=8000,
        usage=usage,
    ).strip()
    if content:
        conn.execute(
            "INSERT INTO taste_profiles (content_md, ratings_count_at_generation) VALUES (?, ?)",
            (content, total_ratings),
        )
        conn.commit()
        stats["regenerated"] = True
    return stats

"""Shared context helpers used by triage, ranking, and discovery prompts."""
from __future__ import annotations

import re
import sqlite3
from urllib.parse import unquote, urlsplit


def get_latest_profile(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM taste_profiles ORDER BY id DESC LIMIT 1"
    ).fetchone()


def active_instructions(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM instructions WHERE status = 'active' ORDER BY created_at"
    ).fetchall()


def format_instructions(rows: list[sqlite3.Row]) -> str:
    if not rows:
        return "(none)"
    lines = []
    for r in rows:
        kind = "SHORT-TERM QUEST" if r["kind"] == "quest" else "STANDING PREFERENCE"
        lines.append(f"- [{kind}, id={r['id']}] {r['text']}")
    return "\n".join(lines)


def profile_text(conn: sqlite3.Connection) -> str:
    row = get_latest_profile(conn)
    return row["content_md"] if row else "(no taste profile yet)"


def set_item_state(conn: sqlite3.Connection, item_id: int, state: str) -> None:
    conn.execute(
        "UPDATE items SET state = ?, state_changed_at = datetime('now') WHERE id = ?",
        (state, item_id),
    )


def title_from_url(url: str) -> str:
    """Best-effort human-readable title from a URL slug."""
    path = unquote(urlsplit(url).path).strip("/")
    slug = path.rsplit("/", 1)[-1] if path else urlsplit(url).netloc
    slug = re.sub(r"\.(html?|php|aspx?)$", "", slug)
    words = [w for w in re.split(r"[-_+\s]+", slug) if w]
    cleaned = " ".join(words)
    return (cleaned[:1].upper() + cleaned[1:]) if cleaned else url

"""Fetch article pages and extract readable text with trafilatura; content-hash dedup."""
from __future__ import annotations

import hashlib
import sqlite3

import httpx
import trafilatura

from ..config import CONTENT_MAX_CHARS, USER_AGENT
from .common import set_item_state

HEADERS = {"User-Agent": USER_AGENT}


def fetch_title_and_text(url: str) -> "tuple[str | None, str]":
    """Fetch a page and return (title, extracted_text). Used for user-added links."""
    import re
    from html import unescape

    resp = httpx.get(url, headers=HEADERS, follow_redirects=True, timeout=30)
    resp.raise_for_status()
    html = resp.text
    text = trafilatura.extract(html, url=url) or ""
    title = None
    try:
        meta = trafilatura.extract_metadata(html)
        title = getattr(meta, "title", None)
    except Exception:
        pass
    if not title:
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        if m:
            title = " ".join(unescape(m.group(1)).split())
    return title, text[:CONTENT_MAX_CHARS]


def _content_hash(text: str) -> str | None:
    normalized = " ".join(text.lower().split())
    if len(normalized) < 200:
        return None
    return hashlib.sha256(normalized.encode()).hexdigest()


def extract_pending(conn: sqlite3.Connection, limit: int = 50) -> dict:
    stats = {"extracted": 0, "failed": 0, "deduped": 0}
    rows = conn.execute(
        "SELECT id, url FROM items WHERE content_text IS NULL AND state = 'new' "
        "ORDER BY id LIMIT ?",
        (limit,),
    ).fetchall()
    for row in rows:
        text = ""
        try:
            resp = httpx.get(row["url"], headers=HEADERS, follow_redirects=True, timeout=30)
            resp.raise_for_status()
            text = trafilatura.extract(resp.text, url=row["url"]) or ""
        except Exception:
            stats["failed"] += 1
        text = text[:CONTENT_MAX_CHARS]
        h = _content_hash(text)
        if h:
            dupe = conn.execute(
                "SELECT id FROM items WHERE content_hash = ? AND id != ?", (h, row["id"])
            ).fetchone()
            if dupe:
                conn.execute(
                    "UPDATE items SET content_text = ?, content_hash = ? WHERE id = ?",
                    (text, h, row["id"]),
                )
                set_item_state(conn, row["id"], "filtered")
                stats["deduped"] += 1
                continue
        # Store '' (not NULL) on failure so we don't refetch forever; triage falls back to title.
        conn.execute(
            "UPDATE items SET content_text = ?, content_hash = ? WHERE id = ?",
            (text, h, row["id"]),
        )
        if text:
            stats["extracted"] += 1
    conn.commit()
    return stats

"""Seed the default sources (idempotent — keyed on URL)."""
from __future__ import annotations

import sqlite3

# (name, kind, url, feed_url, filter_note)
DEFAULT_SOURCES = [
    (
        "Anthropic News",
        "html_list",
        "https://www.anthropic.com/news",
        None,
        None,
    ),
    (
        "Anthropic Research",
        "html_list",
        "https://www.anthropic.com/research",
        None,
        None,
    ),
    (
        "METR",
        "html_list",
        "https://metr.org/blog",
        None,
        None,
    ),
    (
        "Don't Worry About the Vase (Zvi)",
        "rss",
        "https://thezvi.substack.com",
        "https://thezvi.substack.com/feed",
        "Only AI-related posts. Skip posts on other topics (medicine, housing, fertility, "
        "childhood, etc.) unless they are substantially about AI.",
    ),
    (
        "AI Futures Project",
        "rss",
        "https://blog.ai-futures.org",
        "https://blog.aifutures.org/feed",
        None,
    ),
    (
        "Forethought",
        "rss",
        "https://www.forethought.org/research",
        "https://www.forethought.org/feed",
        None,
    ),
]


def seed_defaults(conn: sqlite3.Connection) -> None:
    for name, kind, url, feed_url, filter_note in DEFAULT_SOURCES:
        conn.execute(
            """INSERT OR IGNORE INTO sources (name, kind, url, feed_url, origin, filter_note)
               VALUES (?, ?, ?, ?, 'default', ?)""",
            (name, kind, url, feed_url, filter_note),
        )
    conn.commit()


if __name__ == "__main__":
    from .db import connect, migrate

    migrate()
    conn = connect()
    seed_defaults(conn)
    print("seeded default sources")

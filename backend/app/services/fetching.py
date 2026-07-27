"""Fetching new items from sources: RSS via feedparser, non-RSS listing pages via
a small Haiku extraction call (no per-site CSS selectors)."""
from __future__ import annotations

import re
import sqlite3
import time
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import feedparser
import httpx

from ..config import TRIAGE_MODEL, USER_AGENT
from ..schemas import ListingResult
from . import llm

HEADERS = {"User-Agent": USER_AGENT}
TRACKING_PARAMS = {"ref", "source", "fbclid", "gclid", "mc_cid", "mc_eid", "s"}


def canonicalize_url(url: str) -> str:
    s = urlsplit(url.strip())
    query = [
        (k, v)
        for k, v in parse_qsl(s.query, keep_blank_values=True)
        if not k.startswith("utm_") and k not in TRACKING_PARAMS
    ]
    path = s.path.rstrip("/") or "/"
    return urlunsplit(
        ((s.scheme or "https").lower(), s.netloc.lower(), path, urlencode(query), "")
    )


class _TextCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def strip_html(html: str) -> str:
    p = _TextCollector()
    try:
        p.feed(html)
    except Exception:
        return re.sub(r"<[^>]+>", " ", html)
    return " ".join(" ".join(p.parts).split())


class _AnchorCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.anchors: list[tuple[str, str]] = []
        self._href: str | None = None
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "a":
            self._flush()
            self._href = dict(attrs).get("href")
            self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._buf.append(data)

    def _flush(self) -> None:
        if self._href:
            text = " ".join("".join(self._buf).split())
            self.anchors.append((self._href, text))
        self._href = None
        self._buf = []


def extract_anchors(html: str, base_url: str) -> list[tuple[str, str]]:
    p = _AnchorCollector()
    try:
        p.feed(html)
        p._flush()
    except Exception:
        pass
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for href, text in p.anchors:
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        absolute = urljoin(base_url, href)
        if not absolute.startswith("http"):
            continue
        key = canonicalize_url(absolute)
        if key in seen:
            continue
        seen.add(key)
        out.append((absolute, text[:200]))
    return out


def insert_item(
    conn: sqlite3.Connection,
    *,
    url: str,
    title: str,
    source_id: int | None = None,
    author: str | None = None,
    published_at: str | None = None,
    found_by: str = "source_fetch",
    discovery_instruction_id: int | None = None,
    content_text: str | None = None,
) -> int | None:
    """Insert an item, deduplicating on canonical URL. Returns new id or None if duplicate."""
    canon = canonicalize_url(url)
    cur = conn.execute(
        """INSERT OR IGNORE INTO items
           (source_id, url, canonical_url, title, author, published_at, found_by,
            discovery_instruction_id, content_text)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            source_id,
            url,
            canon,
            title.strip()[:500] or url,
            author,
            published_at,
            found_by,
            discovery_instruction_id,
            content_text,
        ),
    )
    return cur.lastrowid if cur.rowcount else None


def add_user_item(conn: sqlite3.Connection, url: str) -> int:
    """Insert a link the user saved manually. If it already exists but was
    dismissed/filtered, revive it — an explicit add overrides earlier judgments."""
    from .common import set_item_state
    from .extraction import fetch_title_and_text

    canon = canonicalize_url(url)
    existing = conn.execute(
        "SELECT id, state, triage_score FROM items WHERE canonical_url = ?", (canon,)
    ).fetchone()
    if existing:
        if existing["state"] in ("dismissed", "filtered"):
            revived = "triaged" if existing["triage_score"] is not None else "new"
            set_item_state(conn, existing["id"], revived)
        conn.execute("UPDATE items SET found_by = 'user' WHERE id = ?", (existing["id"],))
        return existing["id"]
    title, text = fetch_title_and_text(url)
    item_id = insert_item(
        conn,
        url=url,
        title=title or url,
        found_by="user",
        content_text=text or None,
    )
    assert item_id is not None  # no canonical duplicate exists at this point
    return item_id


def _struct_time_to_iso(t) -> str | None:
    if not t:
        return None
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%S", t)
    except Exception:
        return None


def fetch_rss_source(conn: sqlite3.Connection, source: sqlite3.Row) -> int:
    feed_url = source["feed_url"] or source["url"]
    d = feedparser.parse(
        feed_url,
        etag=source["etag"],
        modified=source["last_modified"],
        agent=USER_AGENT,
    )
    if getattr(d, "status", None) == 304:
        return 0
    if getattr(d, "bozo", False) and not d.entries:
        raise RuntimeError(f"feed parse failed: {getattr(d, 'bozo_exception', 'unknown')}")
    new_count = 0
    for entry in d.entries:
        link = entry.get("link")
        title = entry.get("title") or link
        if not link:
            continue
        published = _struct_time_to_iso(
            entry.get("published_parsed") or entry.get("updated_parsed")
        )
        html = ""
        if entry.get("content"):
            html = entry["content"][0].get("value", "")
        elif entry.get("summary"):
            html = entry["summary"]
        text = strip_html(html) if html else ""
        # Substack (and similar) put full content in the feed; keep it and skip scraping.
        content = text if len(text) > 500 else None
        item_id = insert_item(
            conn,
            url=link,
            title=title,
            source_id=source["id"],
            author=entry.get("author"),
            published_at=published,
            content_text=content,
        )
        if item_id:
            new_count += 1
    conn.execute(
        "UPDATE sources SET etag = ?, last_modified = ? WHERE id = ?",
        (getattr(d, "etag", None), getattr(d, "modified", None), source["id"]),
    )
    return new_count


LISTING_SYSTEM = (
    "You extract article links from a website's listing/index page. Given a list of links "
    "(URL and anchor text) from the page, identify the ones that point to individual "
    "articles, papers, blog posts, or announcements. Exclude navigation, category pages, "
    "social links, legal pages, tag pages, author pages, and pagination. Return the article "
    "links with cleaned-up titles, most recent first if order is apparent. Include a "
    "published date (ISO format) only if it is evident from the anchor text."
)


def fetch_html_list_source(
    conn: sqlite3.Connection, source: sqlite3.Row, usage: llm.UsageTracker
) -> int:
    resp = httpx.get(source["url"], headers=HEADERS, follow_redirects=True, timeout=30)
    resp.raise_for_status()
    anchors = extract_anchors(resp.text, str(resp.url))
    if not anchors:
        raise RuntimeError("no links found on listing page (possibly JS-rendered)")
    # Pre-filter what we already have, so Haiku only sees potentially-new links.
    known = {
        r["canonical_url"]
        for r in conn.execute(
            "SELECT canonical_url FROM items WHERE source_id = ?", (source["id"],)
        )
    }
    candidates = [
        (u, t) for u, t in anchors if canonicalize_url(u) not in known
    ][:250]
    if not candidates:
        return 0
    listing_text = "\n".join(f"{u} | {t}" for u, t in candidates)
    result = llm.parse_structured(
        model=TRIAGE_MODEL,
        system=LISTING_SYSTEM,
        user_content=(
            f"Listing page: {source['url']} (source name: {source['name']})\n\n"
            f"Links (URL | anchor text):\n{listing_text}"
        ),
        output_model=ListingResult,
        max_tokens=4000,
        usage=usage,
    )
    new_count = 0
    for it in result.items[:40]:
        item_id = insert_item(
            conn,
            url=it.url,
            title=it.title,
            source_id=source["id"],
            published_at=it.published,
        )
        if item_id:
            new_count += 1
    return new_count


def fetch_all_sources(
    conn: sqlite3.Connection, usage: llm.UsageTracker, llm_available: bool
) -> dict:
    """Fetch every active source. Per-source failures are recorded, never fatal."""
    stats = {"sources_ok": 0, "sources_failed": 0, "new_items": 0}
    sources = conn.execute(
        "SELECT * FROM sources WHERE status = 'active' ORDER BY id"
    ).fetchall()
    for source in sources:
        try:
            if source["kind"] == "rss":
                new = fetch_rss_source(conn, source)
            else:
                if not llm_available:
                    raise RuntimeError("html_list sources need LLM credentials to parse listings")
                new = fetch_html_list_source(conn, source, usage)
            conn.execute(
                """UPDATE sources SET last_fetched_at = datetime('now'),
                   last_fetch_status = 'ok', last_fetch_error = NULL WHERE id = ?""",
                (source["id"],),
            )
            stats["sources_ok"] += 1
            stats["new_items"] += new
        except Exception as e:  # noqa: BLE001 - one bad source must not kill the run
            conn.execute(
                """UPDATE sources SET last_fetched_at = datetime('now'),
                   last_fetch_status = 'error', last_fetch_error = ? WHERE id = ?""",
                (str(e)[:500], source["id"]),
            )
            stats["sources_failed"] += 1
        conn.commit()
    return stats


def probe_feed(url: str) -> tuple[str, str | None]:
    """Given a site URL, find its RSS/Atom feed. Returns (kind, feed_url)."""
    candidates: list[str] = []
    base = url
    try:
        resp = httpx.get(url, headers=HEADERS, follow_redirects=True, timeout=20)
        base = str(resp.url)
        for tag in re.findall(r"<link[^>]+>", resp.text[:200_000], re.I):
            if re.search(r'type=["\']application/(rss|atom)\+xml["\']', tag, re.I):
                m = re.search(r'href=["\']([^"\']+)["\']', tag)
                if m:
                    candidates.append(urljoin(base, m.group(1)))
    except Exception:
        pass
    for suffix in ("/feed", "/rss", "/feed.xml", "/atom.xml", "/index.xml", "/rss.xml"):
        candidates.append(urljoin(base.rstrip("/") + "/", "." + suffix))
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            d = feedparser.parse(candidate, agent=USER_AGENT)
            if d.entries:
                return ("rss", candidate)
        except Exception:
            continue
    return ("html_list", None)

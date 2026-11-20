"""Fetch article pages and extract readable text with trafilatura; content-hash dedup."""
from __future__ import annotations

import hashlib
import io
import logging
import re
import sqlite3
from html import unescape

import httpx
import trafilatura
from pypdf import PdfReader

from ..config import CONTENT_MAX_CHARS, USER_AGENT
from .common import set_item_state, title_from_url
from .fetching import strip_html

HEADERS = {"User-Agent": USER_AGENT}
# pypdf warns at length about every font it cannot fully decode; that would flood the pipeline log.
logging.getLogger("pypdf").setLevel(logging.ERROR)


ARXIV_PDF = re.compile(r"^https?://(?:www\.)?arxiv\.org/pdf/([^?#]+?)(?:\.pdf)?(?:[?#].*)?$", re.I)
GOOGLE_DOC = re.compile(r"^https?://docs\.google\.com/document/d/([\w-]+)", re.I)
# LessWrong and the Alignment Forum render the post body with JavaScript: a plain fetch of the
# page gives trafilatura only the comments (checked 2026-11-20), so triage was judging saved
# posts by their comment threads. Both sites serve the post itself from /graphql.
FORUM_POST = re.compile(r"^https?://(www\.lesswrong\.com|www\.alignmentforum\.org)/posts/(\w+)", re.I)
PDF_MAX_PAGES = 40


def _get(url: str) -> httpx.Response:
    resp = httpx.get(url, headers=HEADERS, follow_redirects=True, timeout=30)
    resp.raise_for_status()
    return resp


def _html_title(html: str) -> "str | None":
    # og:title first — it's server-rendered and reliable even on JS-heavy sites
    # (trafilatura's metadata guess can grab stray numbers, e.g. LessWrong karma).
    title = None
    m = re.search(
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', html, re.I
    ) or re.search(
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']', html, re.I
    )
    if m:
        title = unescape(m.group(1)).strip()
    if not title or title.isdigit():
        try:
            meta = trafilatura.extract_metadata(html)
            title = getattr(meta, "title", None)
        except Exception:
            pass
    if not title or title.isdigit():
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        if m:
            title = " ".join(unescape(m.group(1)).split())
    if title and title.isdigit():
        title = None
    return title


def _pdf_title_and_text(data: bytes) -> "tuple[str | None, str]":
    """Text of a PDF's first pages (pypdf). A scanned or broken PDF gives ''."""
    try:
        reader = PdfReader(io.BytesIO(data))
        parts: list[str] = []
        total = 0
        for page in reader.pages[:PDF_MAX_PAGES]:
            t = page.extract_text() or ""
            parts.append(t)
            total += len(t)
            if total >= CONTENT_MAX_CHARS:
                break
        title = (reader.metadata.title if reader.metadata else None) or None
    except Exception:  # noqa: BLE001 - encrypted, truncated or malformed file
        return None, ""
    lines = [" ".join(l.split()) for l in "\n".join(parts).replace("\x00", "").splitlines()]
    lines = [l for l in lines if l]
    # Some PDFs come out one word per line; join those so the text reads as prose.
    short = lines and sum(map(len, lines)) / len(lines) < 15
    text = (" " if short else "\n").join(lines)
    # The title field is often the authoring tool's file name ("Microsoft Word - draft3.docx").
    if title:
        title = " ".join(title.split())
        if len(title) < 8 or re.search(r"\.(docx?|tex|indd|pdf|pptx?)$|^(microsoft word|untitled)", title, re.I):
            title = None
    return title, text


def fetch_title_and_text(url: str) -> "tuple[str | None, str]":
    """Fetch a page and return (title, readable text). Raises on a failed download.
    Handles what a plain HTML fetch gets nothing from: PDFs (text via pypdf, and for arXiv the
    title from the abstract page) and Google Docs (the plain-text export; the page itself is
    only a "JavaScript required" shell, which is what item 2118 was), and LessWrong and
    Alignment Forum posts (see FORUM_POST)."""
    doc = GOOGLE_DOC.match(url)
    if doc:
        text = _get(f"https://docs.google.com/document/d/{doc.group(1)}/export?format=txt").text
        try:
            title = _html_title(_get(url).text)
        except Exception:  # noqa: BLE001 - the text is what matters
            title = None
        if title:
            title = re.sub(r"\s*-\s*Google Docs$", "", title)
        return title, text.lstrip("﻿")[:CONTENT_MAX_CHARS]

    post = FORUM_POST.match(url)
    if post:
        try:
            r = httpx.post(
                f"https://{post.group(1)}/graphql", headers=HEADERS, timeout=30,
                json={"query": "query($id:String){post(input:{selector:{_id:$id}}){result{title htmlBody}}}",
                      "variables": {"id": post.group(2)}},
            )
            result = r.json()["data"]["post"]["result"]
            text = strip_html(result["htmlBody"] or "")
            if text:
                return result["title"], text[:CONTENT_MAX_CHARS]
        except httpx.TransportError:
            raise
        except Exception:  # noqa: BLE001 - API changed or post not public: fall back to the page
            pass

    resp = _get(url)
    if "application/pdf" in resp.headers.get("content-type", "").lower() or resp.content[:5] == b"%PDF-":
        title, text = _pdf_title_and_text(resp.content)
        arxiv = ARXIV_PDF.match(url)
        if arxiv:
            try:
                title = _html_title(_get(f"https://arxiv.org/abs/{arxiv.group(1)}").text) or title
            except Exception:  # noqa: BLE001
                pass
        return title, text[:CONTENT_MAX_CHARS]

    html = resp.text
    text = trafilatura.extract(html, url=url) or ""
    return _html_title(html), text[:CONTENT_MAX_CHARS]


def _content_hash(text: str) -> str | None:
    normalized = " ".join(text.lower().split())
    if len(normalized) < 200:
        return None
    return hashlib.sha256(normalized.encode()).hexdigest()


def extract_pending(conn: sqlite3.Connection, limit: int = 50) -> dict:
    stats = {"extracted": 0, "failed": 0, "deduped": 0}
    rows = conn.execute(
        "SELECT id, url, title, found_by, discovered_at < datetime('now', '-2 days') AS old "
        "FROM items WHERE content_text IS NULL AND state = 'new' "
        "ORDER BY id LIMIT ?",
        (limit,),
    ).fetchall()
    for row in rows:
        text = ""
        try:
            title, text = fetch_title_and_text(row["url"])
            # A saved link whose first fetch failed has a title made from its URL; replace it.
            if title and row["found_by"] == "user" and row["title"] == title_from_url(row["url"]):
                conn.execute("UPDATE items SET title = ? WHERE id = ?", (title[:500], row["id"]))
        except httpx.TransportError:
            # No connection or a timeout says nothing about the page. Storing '' here would be
            # permanent: the item is then triaged from its title alone and never fetched again.
            # Leave it NULL so the next run retries, for two days, then give up as below.
            stats["failed"] += 1
            if not row["old"]:
                continue
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

import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ..schemas import SourceIn, SourcePatch
from ..services.fetching import probe_feed
from .deps import get_db

router = APIRouter()


@router.get("/sources")
def list_sources(conn: sqlite3.Connection = Depends(get_db)):
    rows = conn.execute("SELECT * FROM sources ORDER BY id").fetchall()
    return [dict(r) for r in rows]


@router.post("/sources", status_code=201)
def add_source(body: SourceIn, conn: sqlite3.Connection = Depends(get_db)):
    url = body.url.strip()
    if not url.startswith("http"):
        url = "https://" + url
    existing = conn.execute("SELECT id FROM sources WHERE url = ?", (url,)).fetchone()
    if existing:
        raise HTTPException(409, "source already exists")
    kind, feed_url = probe_feed(url)
    name = body.name or url.split("//", 1)[-1].split("/", 1)[0]
    cur = conn.execute(
        """INSERT INTO sources (name, kind, url, feed_url, origin, filter_note)
           VALUES (?, ?, ?, ?, 'user', ?)""",
        (name, kind, url, feed_url, body.filter_note),
    )
    row = conn.execute("SELECT * FROM sources WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(row)


@router.patch("/sources/{source_id}")
def patch_source(
    source_id: int, body: SourcePatch, conn: sqlite3.Connection = Depends(get_db)
):
    row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
    if not row:
        raise HTTPException(404, "source not found")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if "status" in updates and updates["status"] not in ("active", "paused"):
        raise HTTPException(400, "status must be 'active' or 'paused'")
    if "kind" in updates and updates["kind"] not in ("rss", "html_list"):
        raise HTTPException(400, "kind must be 'rss' or 'html_list'")
    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(
            f"UPDATE sources SET {set_clause} WHERE id = ?",
            (*updates.values(), source_id),
        )
    row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
    return dict(row)


@router.get("/proposals")
def list_proposals(conn: sqlite3.Connection = Depends(get_db)):
    rows = conn.execute(
        "SELECT * FROM source_proposals WHERE status = 'pending' ORDER BY id"
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["sample_item_urls"] = json.loads(r["sample_item_urls"] or "[]")
        out.append(d)
    return out


@router.post("/proposals/{proposal_id}/approve")
def approve_proposal(proposal_id: int, conn: sqlite3.Connection = Depends(get_db)):
    row = conn.execute(
        "SELECT * FROM source_proposals WHERE id = ? AND status = 'pending'",
        (proposal_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "pending proposal not found")
    feed_url = row["feed_url"]
    kind = "rss" if feed_url else None
    if kind is None:
        kind, feed_url = probe_feed(row["url"])
    name = row["name"] or row["url"]
    existing = conn.execute(
        "SELECT id FROM sources WHERE url = ?", (row["url"],)
    ).fetchone()
    if existing:
        source_id = existing["id"]
    else:
        cur = conn.execute(
            """INSERT INTO sources (name, kind, url, feed_url, origin)
               VALUES (?, ?, ?, ?, 'agent')""",
            (name, kind, row["url"], feed_url),
        )
        source_id = cur.lastrowid
    conn.execute(
        """UPDATE source_proposals SET status = 'approved', decided_at = datetime('now'),
           created_source_id = ? WHERE id = ?""",
        (source_id, proposal_id),
    )
    return {"ok": True, "source_id": source_id}


@router.post("/proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: int, conn: sqlite3.Connection = Depends(get_db)):
    cur = conn.execute(
        """UPDATE source_proposals SET status = 'rejected', decided_at = datetime('now')
           WHERE id = ? AND status = 'pending'""",
        (proposal_id,),
    )
    if not cur.rowcount:
        raise HTTPException(404, "pending proposal not found")
    return {"ok": True}

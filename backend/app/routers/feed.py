from __future__ import annotations

import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ..config import has_llm_credentials
from ..schemas import LinkIn, ProfileIn, RatingIn, StateIn
from ..services.common import get_latest_profile, set_item_state
from ..services.fetching import add_user_item
from ..services.triage import triage_single
from .deps import get_db

router = APIRouter()

# Read-but-unrated items stay visible so the user can still rate them.
_VISIBLE = (
    "(i.state = 'shown' OR i.state = 'triaged' OR "
    "(i.state = 'read' AND NOT EXISTS (SELECT 1 FROM ratings r WHERE r.item_id = i.id)))"
)


def _latest_rating(conn: sqlite3.Connection, item_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT rating, note, reading_notes FROM ratings WHERE item_id = ? "
        "ORDER BY id DESC LIMIT 1",
        (item_id,),
    ).fetchone()


def _item_dict(conn: sqlite3.Connection, row: sqlite3.Row, extra: dict | None = None) -> dict:
    rating = _latest_rating(conn, row["id"])
    d = {
        "id": row["id"],
        "title": row["title"],
        "url": row["url"],
        "source": row["source_name"]
        or {"discovery": "web discovery", "user": "added by you"}.get(row["found_by"]),
        "published_at": row["published_at"],
        "summary": row["summary"],
        "topics": json.loads(row["topics"]) if row["topics"] else [],
        "state": row["state"],
        "rating": rating["rating"] if rating else None,
        "note": rating["note"] if rating else None,
        "reading_notes": rating["reading_notes"] if rating else None,
        "rank": None,
        "score": None,
        "rationale": None,
        "redundant_with_rank": None,
    }
    if extra:
        d.update(extra)
    return d


@router.get("/feed")
def get_feed(conn: sqlite3.Connection = Depends(get_db)):
    latest = conn.execute(
        "SELECT pipeline_run_id FROM feed_rankings ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if latest:
        run_id = latest["pipeline_run_id"]
        rows = conn.execute(
            f"""SELECT fr.rank, fr.score, fr.rationale, fr.redundant_with_item_id,
                       i.*, s.name AS source_name
                FROM feed_rankings fr
                JOIN items i ON i.id = fr.item_id
                LEFT JOIN sources s ON s.id = i.source_id
                WHERE fr.pipeline_run_id = ? AND {_VISIBLE}
                ORDER BY fr.rank""",
            (run_id,),
        ).fetchall()
        rank_by_item = {r["id"]: r["rank"] for r in rows}
        items = [
            _item_dict(
                conn,
                r,
                {
                    "rank": r["rank"],
                    "score": r["score"],
                    "rationale": r["rationale"],
                    "redundant_with_rank": rank_by_item.get(r["redundant_with_item_id"]),
                },
            )
            for r in rows
        ]
        # User-saved links that haven't been through a ranking run yet go on top —
        # they'd otherwise be invisible until the next pipeline run.
        pending_user = conn.execute(
            """SELECT i.*, s.name AS source_name
               FROM items i LEFT JOIN sources s ON s.id = i.source_id
               WHERE i.found_by = 'user' AND i.state IN ('new', 'triaged')
                 AND i.id NOT IN
                   (SELECT item_id FROM feed_rankings WHERE pipeline_run_id = ?)
               ORDER BY i.discovered_at DESC""",
            (run_id,),
        ).fetchall()
        items = [_item_dict(conn, r) for r in pending_user] + items
        run = conn.execute(
            "SELECT id, status, started_at, finished_at FROM pipeline_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        return {"mode": "ranked", "run": dict(run) if run else None, "items": items}

    # No ranked run yet: chronological fallback (phase-1 / no-API-key mode).
    rows = conn.execute(
        f"""SELECT i.*, s.name AS source_name
            FROM items i LEFT JOIN sources s ON s.id = i.source_id
            WHERE i.state IN ('new','triaged','shown')
               OR (i.state = 'read' AND NOT EXISTS
                   (SELECT 1 FROM ratings r WHERE r.item_id = i.id))
            ORDER BY COALESCE(i.published_at, i.discovered_at) DESC
            LIMIT 100"""
    ).fetchall()
    return {
        "mode": "chronological",
        "run": None,
        "items": [_item_dict(conn, r) for r in rows],
    }


@router.post("/items", status_code=201)
def add_link(body: LinkIn, conn: sqlite3.Connection = Depends(get_db)):
    url = body.url.strip()
    if not url:
        raise HTTPException(400, "url is required")
    if not url.startswith("http"):
        url = "https://" + url
    try:
        item_id = add_user_item(conn, url)
    except Exception as e:  # noqa: BLE001 - fetch/network failures surface to the UI
        raise HTTPException(422, f"could not fetch that page: {e}")
    conn.commit()
    if has_llm_credentials():
        try:
            triage_single(conn, item_id)  # instant summary; pipeline retries on failure
        except Exception:  # noqa: BLE001
            pass
    row = conn.execute(
        """SELECT i.*, s.name AS source_name
           FROM items i LEFT JOIN sources s ON s.id = i.source_id WHERE i.id = ?""",
        (item_id,),
    ).fetchone()
    return _item_dict(conn, row)


@router.post("/items/{item_id}/state")
def set_state(item_id: int, body: StateIn, conn: sqlite3.Connection = Depends(get_db)):
    if body.state not in ("read", "dismissed"):
        raise HTTPException(400, "state must be 'read' or 'dismissed'")
    row = conn.execute("SELECT id FROM items WHERE id = ?", (item_id,)).fetchone()
    if not row:
        raise HTTPException(404, "item not found")
    set_item_state(conn, item_id, body.state)
    return {"ok": True}


@router.post("/items/{item_id}/rating")
def rate_item(item_id: int, body: RatingIn, conn: sqlite3.Connection = Depends(get_db)):
    if body.rating not in ("critical", "worth_it", "fine", "not_worth", "didnt_finish"):
        raise HTTPException(400, "invalid rating")
    row = conn.execute("SELECT id FROM items WHERE id = ?", (item_id,)).fetchone()
    if not row:
        raise HTTPException(404, "item not found")
    conn.execute(
        "INSERT INTO ratings (item_id, rating, note, reading_notes) VALUES (?, ?, ?, ?)",
        (item_id, body.rating, body.note or None, body.reading_notes or None),
    )
    set_item_state(conn, item_id, "read")
    return {"ok": True}


@router.get("/profile")
def get_profile(conn: sqlite3.Connection = Depends(get_db)):
    row = get_latest_profile(conn)
    if not row:
        return {"content_md": "", "generated_at": None}
    return {"content_md": row["content_md"], "generated_at": row["generated_at"]}


@router.put("/profile")
def put_profile(body: ProfileIn, conn: sqlite3.Connection = Depends(get_db)):
    total = conn.execute("SELECT COUNT(*) AS c FROM ratings").fetchone()["c"]
    conn.execute(
        "INSERT INTO taste_profiles (content_md, ratings_count_at_generation) VALUES (?, ?)",
        (body.content_md, total),
    )
    return {"ok": True}

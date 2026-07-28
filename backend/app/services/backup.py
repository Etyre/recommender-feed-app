"""Backups. The ratings/notes/conversation dataset is the irreplaceable part of this
app — everything else can be re-fetched or regenerated. Strategy:

1. Verified SQLite snapshot per day (sqlite3 online-backup API, then integrity-checked;
   a snapshot that fails verification is deleted, and a live DB that fails
   integrity_check NEVER overwrites existing backups).
2. Plain-JSON export of the precious tables — readable forever, immune to SQLite
   corruption, and directly usable by any future recommendation engine.
3. Both mirrored off-machine to iCloud Drive (or FEEDAPP_BACKUP_MIRROR).
4. 30 days of dated snapshots retained locally and on the mirror.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from ..config import DATA_DIR

BACKUP_DIR = DATA_DIR / "backups"
RETAIN_DAYS = 30

PRECIOUS_TABLES = {
    "ratings": "SELECT * FROM ratings ORDER BY id",
    "items": (
        "SELECT id, url, canonical_url, title, author, published_at, discovered_at, "
        "found_by, summary, topics, triage_score, state FROM items ORDER BY id"
    ),
    "instructions": "SELECT * FROM instructions ORDER BY id",
    "conversation_messages": "SELECT * FROM conversation_messages ORDER BY id",
    "taste_profiles": "SELECT * FROM taste_profiles ORDER BY id",
    "sources": "SELECT * FROM sources ORDER BY id",
    "source_proposals": "SELECT * FROM source_proposals ORDER BY id",
}


def mirror_dir() -> Path | None:
    env = os.environ.get("FEEDAPP_BACKUP_MIRROR")
    if env:
        return Path(env).expanduser()
    icloud = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs"
    if icloud.is_dir():
        return icloud / "FeedAppBackups"
    return None


def _quick_check(conn: sqlite3.Connection) -> bool:
    try:
        return conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    except sqlite3.Error:
        return False


def _prune(directory: Path) -> int:
    cutoff = (date.today() - timedelta(days=RETAIN_DAYS)).isoformat()
    removed = 0
    for pattern in ("feed-*.db", "export-*.json"):
        for path in directory.glob(pattern):
            stamp = path.stem.split("-", 1)[1]
            if stamp < cutoff:
                path.unlink(missing_ok=True)
                removed += 1
    return removed


def run_backup(conn: sqlite3.Connection) -> dict:
    stats: dict = {"db_snapshot": None, "export": None, "mirrored_to": None, "pruned": 0}

    # A corrupt live DB must never overwrite good history — fail loudly instead.
    if not _quick_check(conn):
        raise RuntimeError(
            "live database FAILED integrity check — existing backups left untouched; "
            "restore from data/backups/ before writing anything else"
        )

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    day = date.today().isoformat()

    # 1. Verified SQLite snapshot (online backup API is WAL-safe on a live DB).
    snapshot_path = BACKUP_DIR / f"feed-{day}.db"
    tmp_path = BACKUP_DIR / f"feed-{day}.db.tmp"
    dest = sqlite3.connect(tmp_path)
    try:
        conn.backup(dest)
        verified = _quick_check(dest)
    finally:
        dest.close()
    if not verified:
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError("backup snapshot failed verification and was discarded")
    tmp_path.replace(snapshot_path)  # atomic: never leaves a half-written snapshot
    stats["db_snapshot"] = str(snapshot_path)

    # 2. Plain-JSON export of the precious tables.
    export = {
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "tables": {
            name: [dict(row) for row in conn.execute(query)]
            for name, query in PRECIOUS_TABLES.items()
        },
    }
    export_path = BACKUP_DIR / f"export-{day}.json"
    tmp_export = export_path.with_suffix(".json.tmp")
    tmp_export.write_text(json.dumps(export, ensure_ascii=False, indent=1))
    tmp_export.replace(export_path)
    stats["export"] = str(export_path)

    stats["pruned"] = _prune(BACKUP_DIR)

    # 3. Off-machine mirror (iCloud syncs it to Apple's servers + other devices).
    mirror = mirror_dir()
    if mirror is not None:
        try:
            mirror.mkdir(parents=True, exist_ok=True)
            shutil.copy2(snapshot_path, mirror / snapshot_path.name)
            shutil.copy2(export_path, mirror / export_path.name)
            _prune(mirror)
            stats["mirrored_to"] = str(mirror)
        except OSError as e:
            stats["mirror_error"] = str(e)[:200]

    return stats

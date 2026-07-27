import sqlite3

from .config import DB_PATH, MIGRATIONS_DIR


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: FastAPI may run a sync dependency and its route
    # handler on different threadpool threads. Each request gets its own
    # connection (never shared concurrently), so this is safe.
    conn = sqlite3.connect(DB_PATH, timeout=5, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def migrate() -> None:
    conn = connect()
    try:
        current = conn.execute("PRAGMA user_version").fetchone()[0]
        for path in sorted(MIGRATIONS_DIR.glob("[0-9]*.sql")):
            version = int(path.name.split("_", 1)[0])
            if version > current:
                conn.executescript(path.read_text())
                conn.execute(f"PRAGMA user_version = {version}")
                conn.commit()
    finally:
        conn.close()

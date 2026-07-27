import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
REPO_ROOT = BACKEND_DIR.parent
DATA_DIR = Path(os.environ.get("FEEDAPP_DATA_DIR", REPO_ROOT / "data"))
DB_PATH = DATA_DIR / "feed.db"
LOG_DIR = DATA_DIR / "logs"
LOCK_PATH = DATA_DIR / "pipeline.lock"
MIGRATIONS_DIR = APP_DIR / "migrations"
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


def _load_env_file() -> None:
    """Load data/.env so the API key works identically under launchd, uvicorn, and manual runs."""
    env_path = DATA_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


_load_env_file()

# Models
TRIAGE_MODEL = "claude-haiku-4-5"
SMART_MODEL = "claude-opus-5"

# Pipeline caps (cost control)
TRIAGE_MAX_ITEMS_PER_RUN = 60
RANKING_MAX_CANDIDATES = 75
DISCOVERY_MAX_ITEMS = 10
DISCOVERY_MAX_SEARCHES = 8
DISCOVERY_WITHOUT_QUESTS = False  # if True, discovery runs even with no active quests
MAX_PENDING_PROPOSALS = 3
AUTO_DISMISS_DAYS = 30
AUTO_DISMISS_MAX_TRIAGE = 3  # items at/below this triage score get auto-dismissed when stale
QUEST_DEFAULT_DAYS = 14
PROFILE_REGEN_MIN_NEW_RATINGS = 8
PROFILE_REGEN_MAX_AGE_DAYS = 14
CONTENT_MAX_CHARS = 30_000
TRIAGE_CONTENT_CHARS = 6_000
STALE_RUN_MINUTES = 60

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) PersonalFeedReader/0.1 "
    "(local single-user reader)"
)


def has_llm_credentials() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))

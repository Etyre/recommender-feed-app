#!/bin/sh
# End-to-end dry run of the pipeline against a throwaway data directory.
#
# Proves migrate -> seed -> fetch (real RSS over the network) -> extract -> backup work,
# without touching the real feed.db, the real .env/API key, or the iCloud backup mirror,
# and checks the LLM-standard plumbing (shared preamble + contact_eli tool) offline.
# LLM stages are skipped because no key is visible inside the temp data dir. Exit 0 = pass.
set -eu
cd "$(dirname "$0")/backend"
PY=.venv/bin/python
TMP=$(mktemp -d /tmp/recommender-feed-test.XXXXXX)
trap 'rm -rf "$TMP"' EXIT
export FEEDAPP_DATA_DIR="$TMP/data"
export FEEDAPP_BACKUP_MIRROR="$TMP/mirror"
export FEEDAPP_APP_LOG="$TMP/app.log"   # keep test lines out of ~/Library/Logs/recommender-feed.log
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN || true
mkdir -p "$FEEDAPP_DATA_DIR"

echo "== 1. LLM standard: preamble + contact tool on every call path (offline)"
$PY - <<'PYEOF'
import sys
sys.path.insert(0, ".")
from app.services import llm
import llm_contact
pre = llm_contact.preamble()
assert llm.with_preamble("MY RULES").startswith(pre), "string system prompt lacks preamble"
assert llm.with_preamble("MY RULES").endswith("MY RULES")
blocks = llm.with_preamble([{"type": "text", "text": "MY RULES", "cache_control": {"type": "ephemeral"}}])
assert blocks[0]["text"].startswith(pre) and blocks[0]["cache_control"], "block system prompt lacks preamble"
assert llm.CONTACT_TOOL["name"] == "contact_eli"
# A fake response carrying an @ELI: line is detected by the shared extractor (no notification sent).
fake = {"content": [{"type": "text", "text": "Sure.\n@ELI: this is a test line"}]}
assert llm_contact.extract(fake) == [("marker", "this is a test line")]
fake_tool = {"content": [{"type": "tool_use", "name": "contact_eli", "input": {"message": "hi"}}]}
assert llm_contact.extract(fake_tool) == [("tool", "hi")]
print("   ok")
PYEOF

echo "== 2. Pipeline dry run in $FEEDAPP_DATA_DIR (no API key: fetch/extract/backup only)"
$PY -m app.pipeline --trigger manual

echo "== 3. Checking results"
$PY - <<'PYEOF'
import json, os, sqlite3, pathlib
data = pathlib.Path(os.environ["FEEDAPP_DATA_DIR"])
conn = sqlite3.connect(data / "feed.db"); conn.row_factory = sqlite3.Row
run = conn.execute("SELECT * FROM pipeline_runs ORDER BY id DESC LIMIT 1").fetchone()
assert run is not None and run["status"] in ("success", "partial"), dict(run) if run else None
assert "no Anthropic credentials" in (run["error"] or ""), "expected the no-credentials notice"
stats = json.loads(run["stats_json"])
assert "fetch" in stats and "backup" in stats, stats
assert conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0] >= 6, "default sources not seeded"
assert stats["backup"]["db_snapshot"] and stats["backup"]["export"], stats["backup"]
assert list((data / "backups").glob("feed-*.db")) and list((data / "backups").glob("export-*.json"))
mirror = pathlib.Path(os.environ["FEEDAPP_BACKUP_MIRROR"])
assert list(mirror.glob("feed-*.db")), "mirror not written"
print(f"   run {run['id']}: {run['status']}; fetch={stats['fetch']}; items={conn.execute('SELECT COUNT(*) FROM items').fetchone()[0]}")
print("   ok")
PYEOF
echo "PASS"

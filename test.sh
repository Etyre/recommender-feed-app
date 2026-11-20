#!/bin/sh
# End-to-end dry run of the pipeline against a throwaway data directory.
#
# Proves migrate -> seed -> fetch (real RSS over the network) -> extract -> backup work,
# without touching the real feed.db, the real .env/API key, or the iCloud backup mirror,
# and checks the LLM-standard plumbing (shared preamble + contact_eli and note_to_eli tools) offline,
# with stubbed model responses and a throwaway LLM inbox (nothing recorded for real, nothing notified).
# LLM stages are skipped because no key is visible inside the temp data dir. Exit 0 = pass.
set -eu
cd "$(dirname "$0")/backend"
PY=.venv/bin/python
TMP=$(mktemp -d /tmp/recommender-feed-test.XXXXXX)
trap 'rm -rf "$TMP"' EXIT
export FEEDAPP_DATA_DIR="$TMP/data"
export FEEDAPP_BACKUP_MIRROR="$TMP/mirror"
export FEEDAPP_APP_LOG="$TMP/app.log"   # keep test lines out of ~/Library/Logs/recommender-feed.log
export LLM_INBOX_DIR="$TMP/inbox"       # llm_contact: records go here and no notification is sent
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

echo "== 1b. note_to_eli carries on, contact_eli still stops (stubbed responses, inbox in $LLM_INBOX_DIR)"
$PY - <<'PYEOF'
import json, os, sys
sys.path.insert(0, ".")
from types import SimpleNamespace
from anthropic.types import Message
from pydantic import BaseModel
from app.services import llm
import llm_contact
assert str(llm_contact.MESSAGES_PATH).startswith(os.environ["LLM_INBOX_DIR"]), "not the throwaway inbox"

def msg(*blocks, stop="end_turn"):
    return Message.model_validate({"id": "msg_test", "type": "message", "role": "assistant", "model": "fake-model",
        "content": list(blocks), "stop_reason": stop, "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1}})
def text(t): return {"type": "text", "text": t}
def tool(name, m, i): return {"type": "tool_use", "id": f"toolu_{i}", "name": name, "input": {"message": m}}

class Fake:
    """Stands in for the Anthropic client: hands out queued responses and keeps what it was sent."""
    def __init__(self, *replies): self.replies, self.sent = list(replies), []
    def create(self, **kw):
        self.sent.append(kw)
        return self.replies.pop(0)
    def parse(self, output_format=None, **kw):
        r = self.create(**kw)
        t = "".join(b.text for b in r.content if b.type == "text")
        r.parsed_output = output_format.model_validate_json(t) if t else None
        return r
def use(*replies):
    fake = Fake(*replies)
    llm.get_client = lambda: SimpleNamespace(messages=fake)
    return fake
def inbox():
    p = llm_contact.MESSAGES_PATH
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []
def names(kw): return [t["name"] for t in kw["tools"]]

# generate_text (triage, profile): a note-only reply leads to a second call and a normal answer.
fake = use(msg(tool("note_to_eli", "test note one", 1), stop="tool_use"), msg(text('```json\n{"a": 1}\n```')))
usage = llm.UsageTracker()
out = llm.generate_text(model="fake-model", system="MY RULES", user_content="item", usage=usage)
assert llm.extract_json_object(out) == {"a": 1}, out
assert len(fake.sent) == 2 and usage.calls == 2, "expected exactly one follow-up call, both counted"
assert names(fake.sent[0])[:2] == ["contact_eli", "note_to_eli"], names(fake.sent[0])
assert fake.sent[0]["system"].startswith(llm_contact.preamble())
assert fake.sent[1]["messages"][-1]["content"] == [
    {"type": "tool_result", "tool_use_id": "toolu_1", "content": llm_contact.NOTE_RESULT_TEXT}]
recs = inbox()
assert [(r["via"], r["halts"], r["message"], r["app"]) for r in recs] == [("note", False, "test note one", "recommender-feed")], recs

# An answer and a note in the same reply: the answer is kept even if the second reply does not repeat it.
fake = use(msg(text('```json\n{"a": 2}\n```'), tool("note_to_eli", "test note two", 2), stop="tool_use"), msg(text("Done.")))
out = llm.generate_text(model="fake-model", system="MY RULES", user_content="item")
assert llm.extract_json_object(out) == {"a": 2} and "test note two" not in out, out
assert len(inbox()) == 2

# Structured output (ranking, listing pages, chat): same, and the note is not the parsed answer.
class Out(BaseModel):
    a: int
fake = use(msg(tool("note_to_eli", "test note three", 3), stop="tool_use"), msg(text('{"a": 3}')))
got = llm.parse_structured(model="fake-model", system="MY RULES", user_content="x", output_model=Out)
assert got.a == 3 and len(fake.sent) == 2 and len(inbox()) == 3

# Web search call (discovery): a note mid-way is answered and the call carries on.
fake = use(msg(tool("note_to_eli", "test note four", 4), stop="tool_use"), msg(text('{"a": 4}')))
out = llm.run_with_web_search(model="fake-model", system="MY RULES", user_content="x", max_uses=1)
assert llm.extract_json_object(out) == {"a": 4} and len(fake.sent) == 2 and len(inbox()) == 4
assert names(fake.sent[0]) == ["contact_eli", "note_to_eli", "web_search"]

# contact_eli still stops: LLMContacted, one halting record, no second call.
fake = use(msg(tool("contact_eli", "test stop", 5), stop="tool_use"), msg(text("never reached")))
try:
    llm.generate_text(model="fake-model", system="MY RULES", user_content="item")
    raise AssertionError("contact_eli did not stop the task")
except llm.LLMContacted as ex:
    assert ex.record["via"] == "tool" and ex.record["message"] == "test stop"
assert len(fake.sent) == 1 and len(inbox()) == 5 and "halts" not in inbox()[-1]

# A note and contact_eli in one reply: both recorded, the task stops. An @ELI: line stops too.
fake = use(msg(tool("note_to_eli", "test note six", 6), tool("contact_eli", "test stop two", 7), stop="tool_use"))
try:
    llm.generate_text(model="fake-model", system="MY RULES", user_content="item")
    raise AssertionError("contact_eli next to a note did not stop the task")
except llm.LLMContacted:
    pass
assert len(fake.sent) == 1 and [r["via"] for r in inbox()[-2:]] == ["note", "tool"]
use(msg(text("@ELI: test marker line")))
try:
    llm.generate_text(model="fake-model", system="MY RULES", user_content="item")
    raise AssertionError("@ELI: line did not stop the task")
except llm.LLMContacted as ex:
    assert ex.record["via"] == "marker"
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

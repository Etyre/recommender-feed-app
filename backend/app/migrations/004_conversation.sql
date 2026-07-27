CREATE TABLE conversation_messages (
  id INTEGER PRIMARY KEY,
  role TEXT NOT NULL CHECK (role IN ('agent','user')),
  content TEXT NOT NULL,
  proposals_json TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- LLM spend outside pipeline runs (e.g. chat turns), so the cost widget stays honest.
CREATE TABLE llm_usage_log (
  id INTEGER PRIMARY KEY,
  context TEXT NOT NULL,
  input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  est_cost_usd REAL NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

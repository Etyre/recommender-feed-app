-- Allow user-added links: found_by gains a 'user' value. SQLite can't alter a
-- CHECK constraint, so rebuild the table.
PRAGMA foreign_keys=OFF;

CREATE TABLE items_new (
  id INTEGER PRIMARY KEY,
  source_id INTEGER REFERENCES sources(id),
  url TEXT NOT NULL,
  canonical_url TEXT NOT NULL,
  title TEXT NOT NULL,
  author TEXT,
  published_at TEXT,
  discovered_at TEXT NOT NULL DEFAULT (datetime('now')),
  found_by TEXT NOT NULL DEFAULT 'source_fetch'
    CHECK (found_by IN ('source_fetch','discovery','user')),
  discovery_instruction_id INTEGER REFERENCES instructions(id),
  content_text TEXT,
  content_hash TEXT,
  summary TEXT,
  topics TEXT,
  triage_score INTEGER,
  triage_json TEXT,
  state TEXT NOT NULL DEFAULT 'new'
    CHECK (state IN ('new','triaged','shown','read','dismissed','filtered')),
  state_changed_at TEXT
);
INSERT INTO items_new SELECT * FROM items;
DROP TABLE items;
ALTER TABLE items_new RENAME TO items;

CREATE UNIQUE INDEX idx_items_canonical ON items(canonical_url);
CREATE INDEX idx_items_state ON items(state);
CREATE INDEX idx_items_hash ON items(content_hash);

PRAGMA foreign_keys=ON;

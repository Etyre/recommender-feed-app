CREATE TABLE sources (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('rss','html_list')),
  url TEXT NOT NULL,
  feed_url TEXT,
  origin TEXT NOT NULL DEFAULT 'user' CHECK (origin IN ('default','user','agent')),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused')),
  filter_note TEXT,
  etag TEXT,
  last_modified TEXT,
  last_fetched_at TEXT,
  last_fetch_status TEXT,
  last_fetch_error TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX idx_sources_url ON sources(url);

CREATE TABLE instructions (
  id INTEGER PRIMARY KEY,
  text TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('quest','standing')),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','satisfied','expired','archived')),
  expires_at TEXT,
  agent_status_note TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  resolved_at TEXT
);

CREATE TABLE items (
  id INTEGER PRIMARY KEY,
  source_id INTEGER REFERENCES sources(id),
  url TEXT NOT NULL,
  canonical_url TEXT NOT NULL,
  title TEXT NOT NULL,
  author TEXT,
  published_at TEXT,
  discovered_at TEXT NOT NULL DEFAULT (datetime('now')),
  found_by TEXT NOT NULL DEFAULT 'source_fetch' CHECK (found_by IN ('source_fetch','discovery')),
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
CREATE UNIQUE INDEX idx_items_canonical ON items(canonical_url);
CREATE INDEX idx_items_state ON items(state);
CREATE INDEX idx_items_hash ON items(content_hash);

CREATE TABLE ratings (
  id INTEGER PRIMARY KEY,
  item_id INTEGER NOT NULL REFERENCES items(id),
  rating TEXT NOT NULL CHECK (rating IN ('critical','worth_it','fine','not_worth')),
  note TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_ratings_item ON ratings(item_id);

CREATE TABLE source_proposals (
  id INTEGER PRIMARY KEY,
  name TEXT,
  url TEXT NOT NULL,
  feed_url TEXT,
  rationale TEXT NOT NULL,
  sample_item_urls TEXT,
  proposed_by_instruction_id INTEGER REFERENCES instructions(id),
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  decided_at TEXT,
  created_source_id INTEGER REFERENCES sources(id)
);
CREATE UNIQUE INDEX idx_proposals_pending ON source_proposals(url) WHERE status = 'pending';

CREATE TABLE pipeline_runs (
  id INTEGER PRIMARY KEY,
  trigger TEXT NOT NULL CHECK (trigger IN ('scheduled','manual')),
  status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running','success','partial','error')),
  started_at TEXT NOT NULL DEFAULT (datetime('now')),
  finished_at TEXT,
  stage TEXT,
  stats_json TEXT,
  error TEXT
);

CREATE TABLE feed_rankings (
  id INTEGER PRIMARY KEY,
  pipeline_run_id INTEGER NOT NULL REFERENCES pipeline_runs(id),
  item_id INTEGER NOT NULL REFERENCES items(id),
  rank INTEGER NOT NULL,
  score REAL,
  rationale TEXT NOT NULL,
  redundant_with_item_id INTEGER REFERENCES items(id)
);
CREATE INDEX idx_rankings_run ON feed_rankings(pipeline_run_id);

CREATE TABLE taste_profiles (
  id INTEGER PRIMARY KEY,
  content_md TEXT NOT NULL,
  generated_at TEXT NOT NULL DEFAULT (datetime('now')),
  ratings_count_at_generation INTEGER NOT NULL DEFAULT 0
);

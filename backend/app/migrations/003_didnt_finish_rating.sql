-- Add the 'didnt_finish' rating value (opened but didn't read the whole thing).
PRAGMA foreign_keys=OFF;

CREATE TABLE ratings_new (
  id INTEGER PRIMARY KEY,
  item_id INTEGER NOT NULL REFERENCES items(id),
  rating TEXT NOT NULL
    CHECK (rating IN ('critical','worth_it','fine','not_worth','didnt_finish')),
  note TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
INSERT INTO ratings_new SELECT * FROM ratings;
DROP TABLE ratings;
ALTER TABLE ratings_new RENAME TO ratings;
CREATE INDEX idx_ratings_item ON ratings(item_id);

PRAGMA foreign_keys=ON;

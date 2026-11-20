-- How many times triage got a reply it could not use for this item (no JSON, cut off, refused).
-- After TRIAGE_MAX_ATTEMPTS the item is passed on untriaged instead of being retried every run.
ALTER TABLE items ADD COLUMN triage_attempts INTEGER NOT NULL DEFAULT 0;

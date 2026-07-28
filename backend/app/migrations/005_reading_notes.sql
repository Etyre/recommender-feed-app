-- Ratings carry two optional text channels:
--   note          = the reader talking TO the AI ("this was valuable because...")
--   reading_notes = the reader's raw notes taken while reading (AI infers from them)
ALTER TABLE ratings ADD COLUMN reading_notes TEXT;

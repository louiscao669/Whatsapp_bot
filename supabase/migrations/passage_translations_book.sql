-- Book of a regular passage translation (canonical English name, lower case:
-- 'luke', 'judges', '2 kings'). Assignment matching compares it with the QA
-- item's book, so a Judges 9 question is no longer offered a Luke 9 passage.
-- NULL = uploaded before this column existed; the app reads it as Luke.
-- Also applied at startup by eten_shared.database._run_startup_migrations.
ALTER TABLE passage_translations ADD COLUMN IF NOT EXISTS book varchar(64);

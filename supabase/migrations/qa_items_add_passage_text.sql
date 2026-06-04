-- Optional scripture text for a QA item (set via JSON import or SQL seeds).
alter table qa_items add column if not exists passage_text text;

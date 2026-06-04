-- Run once to remove qa_items.language (language lives on recordings and participants only).
drop index if exists idx_qa_items_language;
alter table qa_items drop column if exists language;

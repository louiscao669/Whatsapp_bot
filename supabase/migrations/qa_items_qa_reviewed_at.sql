alter table qa_items add column if not exists qa_reviewed_at timestamptz;

create index if not exists idx_qa_items_qa_reviewed_at on qa_items(qa_reviewed_at);

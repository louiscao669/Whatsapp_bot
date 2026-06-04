alter table qa_items add column if not exists question_type text not null default 'open';
alter table qa_items add column if not exists mcq_choices jsonb not null default '[]'::jsonb;
alter table qa_items add column if not exists original_question_type text;
alter table qa_items add column if not exists original_mcq_choices jsonb not null default '[]'::jsonb;

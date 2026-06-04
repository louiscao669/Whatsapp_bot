-- QA review workflow: originals for revert, soft-remove from assignment.
alter table qa_items add column if not exists original_question_text text;
alter table qa_items add column if not exists original_expected_answer text;
alter table qa_items add column if not exists review_removed_at timestamptz;

update qa_items
set original_question_text = question_text
where original_question_text is null;

update qa_items
set original_expected_answer = expected_answer
where original_expected_answer is null;

create index if not exists idx_qa_items_review_removed_at
on qa_items(review_removed_at);

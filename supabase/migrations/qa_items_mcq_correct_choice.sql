alter table qa_items add column if not exists mcq_correct_choice text;
alter table qa_items add column if not exists original_mcq_correct_choice text;

update qa_items
set mcq_correct_choice = chr(65 + mcq_correct_index)
where mcq_correct_choice is null
  and mcq_correct_index is not null
  and mcq_correct_index between 0 and 3;

update qa_items
set original_mcq_correct_choice = chr(65 + original_mcq_correct_index)
where original_mcq_correct_choice is null
  and original_mcq_correct_index is not null
  and original_mcq_correct_index between 0 and 3;

alter table qa_items drop constraint if exists ck_qa_items_question_type;
alter table qa_items add constraint ck_qa_items_question_type
    check (question_type in ('open', 'mcq', 'tf'));

alter table qa_items drop constraint if exists ck_qa_items_mcq_correct_index;
alter table qa_items drop constraint if exists ck_qa_items_mcq_correct_choice;
alter table qa_items add constraint ck_qa_items_mcq_correct_choice
    check (mcq_correct_choice is null or mcq_correct_choice in ('A', 'B', 'C', 'D'));

alter table qa_items drop column if exists mcq_correct_index;
alter table qa_items drop column if exists original_mcq_correct_index;

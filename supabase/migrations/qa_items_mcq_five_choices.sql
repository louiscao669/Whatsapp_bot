-- Allow a fifth MCQ option (E): the tier-1 canonical 5-option set ends every MCQ
-- with one "cannot tell from this passage" meta-option. Also applied at startup by
-- eten_shared.database._run_startup_migrations.
alter table qa_items drop constraint if exists ck_qa_items_mcq_correct_choice;
alter table qa_items add constraint ck_qa_items_mcq_correct_choice
    check (mcq_correct_choice is null or mcq_correct_choice in ('A', 'B', 'C', 'D', 'E'));

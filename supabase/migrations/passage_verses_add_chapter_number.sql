alter table passage_verses
    add column if not exists chapter_number integer;

update passage_verses
set chapter_number = 1
where chapter_number is null;

alter table passage_verses
    alter column chapter_number set not null;

alter table passage_verses
    add constraint passage_verses_chapter_number_positive
    check (chapter_number > 0);

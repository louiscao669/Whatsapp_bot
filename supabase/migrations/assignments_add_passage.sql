alter table assignments
    add column if not exists passage_translation_id text
        references passage_translations(id) on delete set null,
    add column if not exists passage_chapter_number integer,
    add column if not exists passage_verse_numbers jsonb not null default '[]'::jsonb,
    add column if not exists passage_text text;

create index if not exists idx_assignments_passage_translation_id
    on assignments(passage_translation_id);

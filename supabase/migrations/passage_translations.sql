create table if not exists passage_translations (
    id text primary key default gen_random_uuid()::text,
    language text not null,
    name text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_passage_translations_language_name unique (language, name)
);

create unique index if not exists uq_passage_translations_unnamed_language
    on passage_translations(language)
    where name is null;

create table if not exists passage_verses (
    id text primary key default gen_random_uuid()::text,
    translation_id text not null references passage_translations(id) on delete cascade,
    verse_number text not null,
    position integer not null,
    text text not null,
    created_at timestamptz not null default now(),
    constraint uq_passage_verses_translation_number unique (translation_id, verse_number),
    constraint uq_passage_verses_translation_position unique (translation_id, position)
);

create index if not exists idx_passage_translations_language
    on passage_translations(language);

create index if not exists idx_passage_verses_translation_id
    on passage_verses(translation_id);

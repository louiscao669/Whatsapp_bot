-- Per-language keyword rubrics for scoring participant responses.

create table if not exists qa_item_language_keywords (
    qa_item_id text not null references qa_items(id) on delete cascade,
    language text not null,
    required_keywords jsonb not null default '[]'::jsonb,
    optional_keywords jsonb not null default '[]'::jsonb,
    required_keyword_specs jsonb not null default '[]'::jsonb,
    optional_keyword_specs jsonb not null default '[]'::jsonb,
    updated_by text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (qa_item_id, language)
);

create index if not exists idx_qa_item_language_keywords_language
    on qa_item_language_keywords(language);

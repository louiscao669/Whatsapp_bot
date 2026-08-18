-- Tier-1 human-pilot units: source-passage variants plus one QA per 3-verse window.

alter table public.experiment_passages
    add column if not exists source_passage_id varchar(128);

update public.experiment_passages
set source_passage_id = 'luke' || chapter::text
where source_passage_id is null;

alter table public.experiment_passages
    drop constraint if exists uq_experiment_passage_chapter_condition_language;

create unique index if not exists uq_experiment_passage_source_condition_language
    on public.experiment_passages (source_passage_id, condition, language);

create index if not exists ix_experiment_passages_source_passage_id
    on public.experiment_passages (source_passage_id);

create table if not exists public.experiment_windows (
    id text primary key default gen_random_uuid()::text,
    qa_item_id text not null references public.qa_items(id) on delete cascade,
    source_passage_id varchar(128) not null,
    content_id varchar(128) not null,
    window_key varchar(255) not null,
    group_index integer not null check (group_index between 1 and 8),
    sequence_index integer not null,
    window_ordinals jsonb not null default '[]'::jsonb,
    verse_numbers jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now(),
    constraint uq_experiment_windows_qa_item unique (qa_item_id),
    constraint uq_experiment_windows_source_window
        unique (source_passage_id, window_key),
    constraint uq_experiment_windows_sequence unique (sequence_index)
);

create index if not exists ix_experiment_windows_group_index
    on public.experiment_windows (group_index);
create index if not exists ix_experiment_windows_source_passage_id
    on public.experiment_windows (source_passage_id);
create index if not exists ix_experiment_windows_qa_item_id
    on public.experiment_windows (qa_item_id);

alter table public.experiment_windows enable row level security;

-- Verse-segmented content owned by each condition-specific experiment passage.
create table if not exists experiment_passage_verses (
    id text primary key default gen_random_uuid()::text,
    experiment_passage_id text not null references experiment_passages(id) on delete cascade,
    verse_number text not null,
    position integer not null,
    text text not null,
    created_at timestamptz not null default now(),
    constraint uq_experiment_passage_verses_number unique (experiment_passage_id, verse_number),
    constraint uq_experiment_passage_verses_position unique (experiment_passage_id, position)
);

create index if not exists idx_experiment_passage_verses_passage_id
    on experiment_passage_verses(experiment_passage_id);

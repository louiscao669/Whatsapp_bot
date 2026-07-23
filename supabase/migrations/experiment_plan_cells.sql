-- Designed-assignment (human pilot): variant passages, Latin-square plan cells,
-- and the FK tying each answered assignment back to the condition it realized.
-- QA is imported once per chapter (QAItems); only the passage varies per
-- condition, so it lives in experiment_passages. See
-- DESIGNED_ASSIGNMENT_EXTENSION_2026-07-20.md.
--
-- Fully idempotent: safe to run on a fresh DB or one where an earlier version
-- of this migration (with a passage_id column on the plan cells) already ran.

-- 1. Variant passages: one (chapter x condition) text, shared across participants.
create table if not exists experiment_passages (
    id text primary key default gen_random_uuid()::text,
    chapter integer not null,
    condition text not null,
    name text,
    language text not null,
    passage_reference text,
    passage_text text not null,
    created_at timestamptz not null default now(),
    constraint uq_experiment_passage_chapter_condition_language unique (chapter, condition, language)
);

-- Add the human-readable name column to an already-created table (no-op on fresh create).
alter table experiment_passages
    add column if not exists name text;
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

-- 2. Plan cells: participant x chapter -> condition + the variant passage to show.
create table if not exists experiment_plan_cells (
    id text primary key default gen_random_uuid()::text,
    participant_id text not null references participants(id) on delete cascade,
    chapter integer not null,
    condition text not null,
    experiment_passage_id text references experiment_passages(id) on delete set null,
    sequence_index integer not null,
    status text not null default 'pending',
    created_at timestamptz not null default now(),
    constraint uq_experiment_plan_participant_chapter unique (participant_id, chapter),
    constraint uq_experiment_plan_participant_sequence unique (participant_id, sequence_index)
);

-- Transition an already-created plan-cells table from the old passage_id column
-- to the experiment_passage_id FK (no-ops on a fresh create above).
alter table experiment_plan_cells
    add column if not exists experiment_passage_id text
        references experiment_passages(id) on delete set null;
alter table experiment_plan_cells
    drop column if exists passage_id;

create index if not exists idx_experiment_plan_cells_participant_id
    on experiment_plan_cells(participant_id);
create index if not exists idx_experiment_plan_cells_passage_id
    on experiment_plan_cells(experiment_passage_id);

-- 3. Nullable FK on assignments: production (coverage-path) assignments leave it
-- null; only the experiment selector stamps it.
alter table assignments
    add column if not exists experiment_cell_id text
        references experiment_plan_cells(id) on delete set null;

create index if not exists idx_assignments_experiment_cell_id
    on assignments(experiment_cell_id);

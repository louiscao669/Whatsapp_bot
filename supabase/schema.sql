create table if not exists participants (
    id text primary key default gen_random_uuid()::text,
    wa_id text not null unique,
    display_name text,
    target_language text,
    locale text,
    timezone text,
    consented boolean not null default false,
    preferred_batch_size integer not null default 3,
    completed_count integer not null default 0,
    last_seen_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists qa_items (
    id text primary key default gen_random_uuid()::text,
    passage_id text not null,
    passage_reference text,
    audio_url text,
    language text not null,
    question_text text not null,
    expected_answer text not null,
    required_keywords jsonb not null default '[]'::jsonb,
    optional_keywords jsonb not null default '[]'::jsonb,
    min_responses_required integer not null default 3,
    active boolean not null default true,
    review_priority integer not null default 0,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists assignments (
    id text primary key default gen_random_uuid()::text,
    participant_id text not null references participants(id) on delete cascade,
    qa_item_id text not null references qa_items(id) on delete cascade,
    batch_id text,
    status text not null default 'assigned',
    assigned_at timestamptz not null default now(),
    started_at timestamptz,
    completed_at timestamptz,
    due_at timestamptz,
    attempt_count integer not null default 0,
    constraint uq_assignments_participant_qa_item unique (participant_id, qa_item_id)
);

create table if not exists participant_responses (
    id text primary key default gen_random_uuid()::text,
    participant_id text not null references participants(id) on delete cascade,
    qa_item_id text not null references qa_items(id) on delete cascade,
    assignment_id text references assignments(id) on delete set null,
    response_type text not null default 'text',
    response_text text,
    media_id text,
    media_url text,
    transcript_text text,
    normalized_text text,
    correctness_score double precision,
    matched_keywords jsonb not null default '[]'::jsonb,
    missing_keywords jsonb not null default '[]'::jsonb,
    is_flagged boolean not null default false,
    flag_reason text,
    review_status text not null default 'pending',
    received_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    constraint ck_participant_responses_correctness_score
        check (correctness_score is null or (correctness_score >= 0 and correctness_score <= 1))
);

create index if not exists idx_participants_wa_id on participants(wa_id);
create index if not exists idx_participants_target_language on participants(target_language);
create index if not exists idx_qa_items_passage_id on qa_items(passage_id);
create index if not exists idx_qa_items_language on qa_items(language);
create index if not exists idx_assignments_batch_id on assignments(batch_id);
create index if not exists idx_assignments_status on assignments(status);
create index if not exists idx_participant_responses_is_flagged on participant_responses(is_flagged);
create index if not exists idx_participant_responses_review_status on participant_responses(review_status);

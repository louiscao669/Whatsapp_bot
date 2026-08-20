-- Human-pilot participant interface (/pilot): per-question active-page timing,
-- immutable experimental provenance, and a scoring timestamp.
--
-- Design notes (see packages/eten-shared/eten_shared/models.py for the full
-- docstrings):
--
--   1. pilot_sessions -- one row per participant's run through /pilot. Holds
--      only the consent version + timestamp the protocol requires; the
--      participant id is already pseudonymous, and no browser fingerprint,
--      IP or user agent is stored.
--
--   2. pilot_question_trials -- the pilot's unit of analysis. Answer text and
--      submission time are NOT copied here: they stay on answer_receipts
--      (immutable, one per assignment), and the verdict stays on
--      participant_responses. What is stored is only what nothing else
--      records -- the visible-page timing, the QC counters and the immutable
--      provenance snapshot.
--
--      status is assigned -> started -> submitted and deliberately does NOT
--      reuse assignments.status: the pilot never expires a question, and the
--      shared assignment lifecycle (which the answer-receipt drain and the
--      messenger surfaces depend on) must not be disturbed. An abandoned
--      question stays 'started'; "incomplete" is derived at report time as
--      started-with-no-receipt. There is no pilot 'expired'.
--
--   3. participant_responses.scored_at -- when a correctness verdict was
--      written. NULL means unscored, which the pilot report treats as missing
--      data, never as a wrong answer. Never use it as a submission time:
--      scoring runs after receipt acceptance and can lag by minutes.

alter table public.participant_responses
    add column if not exists scored_at timestamptz;

create table if not exists public.pilot_sessions (
    id text primary key default gen_random_uuid()::text,
    participant_id text not null references public.participants(id) on delete cascade,
    consent_version varchar(64),
    consented_at timestamptz,
    started_at timestamptz not null default now(),
    completed_at timestamptz,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_pilot_sessions_participant unique (participant_id)
);

create index if not exists ix_pilot_sessions_participant_id
    on public.pilot_sessions (participant_id);

create table if not exists public.pilot_question_trials (
    id text primary key default gen_random_uuid()::text,
    pilot_session_id text not null
        references public.pilot_sessions(id) on delete cascade,
    participant_id text not null references public.participants(id) on delete cascade,
    assignment_id text not null references public.assignments(id) on delete cascade,
    qa_item_id text not null references public.qa_items(id) on delete cascade,
    sequence_index integer not null,
    question_type varchar(16) not null default 'open',
    condition varchar(64),
    status varchar(16) not null default 'assigned',
    started_at timestamptz,
    submitted_at timestamptz,
    active_time_ms integer not null default 0,
    wall_clock_time_ms integer,
    visibility_change_count integer not null default 0,
    reload_count integer not null default 0,
    submission_id varchar(64),
    answer_receipt_id text references public.answer_receipts(id) on delete set null,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    -- One trial per assignment: the pilot presents a question once, and the
    -- answer receipt is likewise one-per-assignment, so the two line up 1:1.
    constraint uq_pilot_trials_assignment unique (assignment_id),
    constraint uq_pilot_trials_session_sequence unique (pilot_session_id, sequence_index),
    constraint ck_pilot_trials_active_time_ms check (active_time_ms >= 0),
    -- Structural guarantee that the pilot cannot expire a question.
    constraint ck_pilot_trials_status
        check (status in ('assigned', 'started', 'submitted'))
);

create index if not exists ix_pilot_question_trials_participant_id
    on public.pilot_question_trials (participant_id);
create index if not exists ix_pilot_question_trials_pilot_session_id
    on public.pilot_question_trials (pilot_session_id);
create index if not exists ix_pilot_question_trials_assignment_id
    on public.pilot_question_trials (assignment_id);
create index if not exists ix_pilot_question_trials_qa_item_id
    on public.pilot_question_trials (qa_item_id);
create index if not exists ix_pilot_question_trials_condition
    on public.pilot_question_trials (condition);
create index if not exists ix_pilot_question_trials_question_type
    on public.pilot_question_trials (question_type);
create index if not exists ix_pilot_question_trials_status
    on public.pilot_question_trials (status);
create index if not exists ix_pilot_question_trials_submission_id
    on public.pilot_question_trials (submission_id);

-- REQUIRED by supabase/migrations/README.md: close the auto-exposed PostgREST
-- surface. The Flask backend connects as the owner role and bypasses RLS, so
-- no policy is needed (and adding one would only re-open the hole).
alter table public.pilot_sessions enable row level security;
alter table public.pilot_question_trials enable row level security;

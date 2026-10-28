-- Human-pilot background & eligibility questionnaire (/pilot, after consent,
-- before the first question). Instrument + rules: eten_shared/pilot_questionnaire.py
-- (IRB: Eligibility_Screening_Questionnaire_EN_v1 + Questionnaire_Administration_Note_EN_v1).
--
--   1. pilot_questionnaire_responses -- one row per ELIGIBLE participant, filled
--      section by section (status = last section saved, eligibility ->
--      background -> religion -> familiarity; completed_at set after Section D). Screened-out participants never get a row.
--   2. pilot_screenout_counts -- the only trace of a screen-out: an anonymous
--      count per instrument version. No participant id, no answers, no timestamp.
--
-- Also applied idempotently at startup by eten_shared.database._run_startup_migrations.

create table if not exists public.pilot_questionnaire_responses (
    id text primary key default gen_random_uuid()::text,
    participant_id text not null references public.participants(id) on delete cascade,
    instrument_version varchar(64) not null,
    language varchar(16) not null,
    status varchar(16) not null,
    eligibility_answers jsonb not null default '{}'::jsonb,
    background_answers jsonb,
    religion_consent boolean,
    religion_answers jsonb,
    familiarity_answers jsonb,
    familiarity_correct integer,
    familiarity_answered integer,
    familiarity_score double precision,
    eligible_at timestamptz not null default now(),
    completed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_pilot_questionnaire_participant unique (participant_id),
    constraint ck_pilot_questionnaire_status
        check (status in ('eligibility', 'background', 'religion', 'familiarity'))
);

create index if not exists ix_pilot_questionnaire_responses_participant_id
    on public.pilot_questionnaire_responses (participant_id);

alter table public.pilot_questionnaire_responses enable row level security;

create table if not exists public.pilot_screenout_counts (
    instrument_version varchar(64) primary key,
    screenouts integer not null default 0
);

alter table public.pilot_screenout_counts enable row level security;

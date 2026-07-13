create table if not exists participants (
    id text primary key default gen_random_uuid()::text,
    display_name text,
    target_language text,
    locale text,
    timezone text,
    profile_photo_uri text,
    dashboard_preferences jsonb not null default '{}'::jsonb,
    consented boolean not null default false,
    preferred_batch_size integer not null default 3,
    completed_count integer not null default 0,
    nudge_platform_sequence jsonb not null default '[]'::jsonb,
    last_seen_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists participant_provider_contacts (
    id text primary key default gen_random_uuid()::text,
    participant_id text not null references participants(id) on delete cascade,
    provider text not null,
    external_user_id text not null,
    display_name text,
    username text,
    first_name text,
    last_name text,
    phone text,
    locale text,
    metadata jsonb not null default '{}'::jsonb,
    opted_in_at timestamptz,
    opted_out_at timestamptz,
    last_seen_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_participant_provider_contacts_provider_external_user_id
        unique (provider, external_user_id)
);

create table if not exists qa_items (
    id text primary key default gen_random_uuid()::text,
    passage_id text not null,
    passage_reference text,
    passage_text text,
    audio_url text,
    question_text text not null,
    question_type text not null default 'open',
    mcq_choices jsonb not null default '[]'::jsonb,
    mcq_correct_choice text,
    expected_answer text not null,
    required_keywords jsonb not null default '[]'::jsonb,
    optional_keywords jsonb not null default '[]'::jsonb,
    required_keyword_specs jsonb not null default '[]'::jsonb,
    optional_keyword_specs jsonb not null default '[]'::jsonb,
    original_required_keywords jsonb not null default '[]'::jsonb,
    original_required_keyword_specs jsonb not null default '[]'::jsonb,
    original_question_text text,
    original_expected_answer text,
    original_question_type text,
    original_mcq_choices jsonb not null default '[]'::jsonb,
    original_mcq_correct_choice text,
    keyword_source text not null default 'answer',
    min_responses_required integer not null default 3,
    active boolean not null default true,
    review_removed_at timestamptz,
    qa_reviewed_at timestamptz,
    review_priority integer not null default 0,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists qa_item_recordings (
    id text primary key default gen_random_uuid()::text,
    qa_item_id text not null references qa_items(id) on delete cascade,
    recording_type text not null,
    language text not null,
    version int not null default 1,
    storage_uri text not null,
    content_type text,
    uploaded_by text,
    created_at timestamptz not null default now(),
    constraint ck_qa_item_recordings_type
        check (recording_type in ('question', 'answer')),
    constraint uq_qa_item_recordings_version
        unique (qa_item_id, recording_type, language, version)
);

-- Existing databases: add version column and backfill before enforcing unique constraint.
-- alter table qa_item_recordings add column if not exists version int not null default 1;
-- with numbered as (
--   select id,
--     row_number() over (
--       partition by qa_item_id, recording_type, language
--       order by created_at asc, id asc
--     ) as version
--   from qa_item_recordings
-- )
-- update qa_item_recordings r
-- set version = numbered.version
-- from numbered
-- where r.id = numbered.id;
-- alter table qa_item_recordings
--   add constraint uq_qa_item_recordings_version
--   unique (qa_item_id, recording_type, language, version);

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

create table if not exists qa_item_keyword_recordings (
    id text primary key default gen_random_uuid()::text,
    qa_item_id text not null references qa_items(id) on delete cascade,
    language text not null,
    keyword_kind text not null,
    keyword_text text not null,
    version int not null default 1,
    storage_uri text not null,
    content_type text,
    uploaded_by text,
    created_at timestamptz not null default now(),
    constraint ck_qa_item_keyword_recordings_kind
        check (keyword_kind in ('required', 'optional')),
    constraint uq_qa_item_keyword_recordings_version
        unique (qa_item_id, language, keyword_kind, keyword_text, version)
);

create table if not exists system_languages (
    code text primary key,
    seen_in_participants boolean not null default false,
    seen_in_recordings boolean not null default false,
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
    is_correct text not null default 'pending',
    flag_reason text,
    review_status text not null default 'pending',
    source_channel text,
    received_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    constraint ck_participant_responses_correctness_score
        check (correctness_score is null or (correctness_score >= 0 and correctness_score <= 1))
);


create table if not exists participant_events (
    id text primary key default gen_random_uuid()::text,
    participant_id text not null references participants(id) on delete cascade,
    event_type text not null,
    source text,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists outbox_notifications (
    id text primary key default gen_random_uuid()::text,
    participant_id text not null references participants(id) on delete cascade,
    notification_type text not null,
    payload jsonb not null default '{}'::jsonb,
    status text not null default 'pending',
    attempt_count integer not null default 0,
    failure_reason text,
    created_at timestamptz not null default now(),
    sent_at timestamptz
);

create table if not exists reminders (
    id text primary key default gen_random_uuid()::text,
    participant_id text not null references participants(id) on delete cascade,
    assignment_id text references assignments(id) on delete set null,
    reminder_type text not null,
    message_text text not null,
    status text not null default 'pending',
    scheduled_for timestamptz not null,
    sent_at timestamptz,
    failure_reason text,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists participant_badges (
    id text primary key default gen_random_uuid()::text,
    participant_id text not null references participants(id) on delete cascade,
    badge_type text not null,
    title text not null,
    description text,
    metadata jsonb not null default '{}'::jsonb,
    awarded_at timestamptz not null default now(),
    constraint uq_participant_badges_participant_badge_type unique (participant_id, badge_type)
);

create table if not exists participant_wallets (
    id text primary key default gen_random_uuid()::text,
    participant_id text not null references participants(id) on delete cascade,
    balance integer not null default 0,
    lifetime_earned integer not null default 0,
    lifetime_spent integer not null default 0,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_participant_wallets_participant unique (participant_id)
);

create table if not exists participant_currency_events (
    id text primary key default gen_random_uuid()::text,
    participant_id text not null references participants(id) on delete cascade,
    wallet_id text references participant_wallets(id) on delete set null,
    assignment_id text references assignments(id) on delete set null,
    response_id text references participant_responses(id) on delete set null,
    amount integer not null,
    balance_after integer not null,
    reason text not null,
    source text,
    source_event_id text,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists participant_sessions (
    id text primary key default gen_random_uuid()::text,
    participant_id text not null references participants(id) on delete cascade,
    current_assignment_id text references assignments(id) on delete set null,
    current_batch_id text,
    state text not null default 'onboarding',
    reminders_enabled boolean not null default true,
    opted_out_at timestamptz,
    last_prompt_sent_at timestamptz,
    last_reminder_sent_at timestamptz,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_participant_sessions_participant unique (participant_id)
);

create table if not exists admin_users (
    id text primary key default gen_random_uuid()::text,
    email text not null unique,
    role text not null check (role in ('admin', 'expert')),
    active boolean not null default true,
    display_name text,
    last_login_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists admin_login_codes (
    id text primary key default gen_random_uuid()::text,
    email text not null,
    code_hash text not null,
    expires_at timestamptz not null,
    consumed_at timestamptz,
    attempts integer not null default 0,
    created_at timestamptz not null default now()
);

create index if not exists idx_participants_target_language on participants(target_language);
create index if not exists idx_participant_provider_contacts_participant_id
    on participant_provider_contacts(participant_id);
create index if not exists idx_participant_provider_contacts_provider
    on participant_provider_contacts(provider);
create index if not exists idx_qa_items_passage_id on qa_items(passage_id);
create index if not exists idx_qa_item_recordings_qa_item_id on qa_item_recordings(qa_item_id);
create index if not exists idx_qa_item_recordings_language on qa_item_recordings(language);
create index if not exists idx_qa_item_recordings_type on qa_item_recordings(recording_type);
create index if not exists idx_qa_item_language_keywords_language
    on qa_item_language_keywords(language);
create index if not exists idx_qa_item_keyword_recordings_qa_item
    on qa_item_keyword_recordings(qa_item_id);
create index if not exists idx_system_languages_code on system_languages(code);
create index if not exists idx_assignments_batch_id on assignments(batch_id);
create index if not exists idx_assignments_status on assignments(status);
create index if not exists idx_participant_responses_is_correct on participant_responses(is_correct);
create index if not exists idx_participant_responses_review_status on participant_responses(review_status);
create index if not exists idx_participant_responses_source_channel on participant_responses(source_channel);
create index if not exists idx_outbox_notifications_participant_id on outbox_notifications(participant_id);
create index if not exists idx_outbox_notifications_status on outbox_notifications(status);
create index if not exists idx_outbox_notifications_notification_type on outbox_notifications(notification_type);
create index if not exists idx_outbox_notifications_created_at on outbox_notifications(created_at);

create index if not exists idx_participant_events_participant_id on participant_events(participant_id);
create index if not exists idx_participant_events_event_type on participant_events(event_type);
create index if not exists idx_reminders_participant_id on reminders(participant_id);
create index if not exists idx_reminders_assignment_id on reminders(assignment_id);
create index if not exists idx_reminders_reminder_type on reminders(reminder_type);
create index if not exists idx_reminders_status on reminders(status);
create index if not exists idx_reminders_scheduled_for on reminders(scheduled_for);
create index if not exists idx_participant_badges_participant_id on participant_badges(participant_id);
create index if not exists idx_participant_badges_badge_type on participant_badges(badge_type);
create index if not exists idx_participant_wallets_participant_id on participant_wallets(participant_id);
create index if not exists idx_participant_currency_events_participant_id
    on participant_currency_events(participant_id);
create index if not exists idx_participant_currency_events_reason
    on participant_currency_events(reason);
create index if not exists idx_participant_currency_events_source_event_id
    on participant_currency_events(source_event_id);
create index if not exists idx_participant_currency_events_created_at
    on participant_currency_events(created_at);
create index if not exists idx_participant_sessions_current_batch_id on participant_sessions(current_batch_id);
create index if not exists idx_participant_sessions_state on participant_sessions(state);
create index if not exists idx_admin_users_email on admin_users(email);
create index if not exists idx_admin_users_role on admin_users(role);
create index if not exists idx_admin_login_codes_email on admin_login_codes(email);
create index if not exists idx_admin_login_codes_expires_at on admin_login_codes(expires_at);

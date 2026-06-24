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

create index if not exists idx_participant_wallets_participant_id
    on participant_wallets(participant_id);
create index if not exists idx_participant_currency_events_participant_id
    on participant_currency_events(participant_id);
create index if not exists idx_participant_currency_events_reason
    on participant_currency_events(reason);
create index if not exists idx_participant_currency_events_source_event_id
    on participant_currency_events(source_event_id);
create index if not exists idx_participant_currency_events_created_at
    on participant_currency_events(created_at);

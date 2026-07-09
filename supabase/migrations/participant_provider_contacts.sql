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

create index if not exists idx_participant_provider_contacts_participant_id
    on participant_provider_contacts(participant_id);

create index if not exists idx_participant_provider_contacts_provider
    on participant_provider_contacts(provider);

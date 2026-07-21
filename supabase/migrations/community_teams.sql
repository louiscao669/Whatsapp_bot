create table if not exists community_teams (
    id text primary key default gen_random_uuid()::text,
    name text not null,
    creator_participant_id text not null references participants(id) on delete cascade,
    target_language text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint community_teams_name_length check (char_length(trim(name)) between 1 and 64)
);

create unique index if not exists uq_community_teams_name_ci
    on community_teams (lower(name));
create index if not exists idx_community_teams_creator
    on community_teams (creator_participant_id);
create index if not exists idx_community_teams_language
    on community_teams (target_language);

create table if not exists community_team_members (
    id text primary key default gen_random_uuid()::text,
    team_id text not null references community_teams(id) on delete cascade,
    participant_id text not null references participants(id) on delete cascade,
    joined_at timestamptz not null default now(),
    constraint uq_community_team_members_participant unique (participant_id)
);

create index if not exists idx_community_team_members_team
    on community_team_members (team_id);
create index if not exists idx_community_team_members_participant
    on community_team_members (participant_id);

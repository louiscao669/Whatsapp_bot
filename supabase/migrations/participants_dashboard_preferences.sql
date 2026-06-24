alter table participants
    add column if not exists dashboard_preferences jsonb not null default '{}'::jsonb;

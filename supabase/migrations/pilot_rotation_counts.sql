create table if not exists public.pilot_rotation_counts (
    rotation integer primary key,
    issued integer not null
);

alter table public.pilot_rotation_counts enable row level security;

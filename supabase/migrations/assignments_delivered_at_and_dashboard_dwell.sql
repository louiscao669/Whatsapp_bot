-- Per-item time + dashboard dwell instrumentation for the platform-engagement
-- experiment (see EXPERIMENT_PLATFORM_ENGAGEMENT_2026-07-12.md). Two additions:
--
--   1. assignments.delivered_at -- when the question was presented / made
--      available to the participant. On the messenger this is the push
--      (== started_at, since a bot receives no "opened" signal); on the
--      dashboard it is stamped when the batch is delivered, which is EARLIER
--      than started_at (the card being opened). This lets analysis separate
--      wait time (delivered->started) from engaged time (started->completed)
--      and gives a uniform delivered->completed per-item latency.
--
--   2. dashboard_engagement_sessions -- accumulated engaged dwell time on the
--      participant dashboard, advanced by a client heartbeat (~15s while the
--      page is visible; gaps capped so a backgrounded tab cannot inflate it).
--      Dashboard-only: Telegram/WhatsApp expose no dwell signal to a bot.

alter table assignments
    add column if not exists delivered_at timestamptz;

create table if not exists dashboard_engagement_sessions (
    id text primary key default gen_random_uuid()::text,
    participant_id text not null references participants(id) on delete cascade,
    session_key text not null,
    started_at timestamptz not null default now(),
    last_heartbeat_at timestamptz not null default now(),
    active_seconds integer not null default 0,
    heartbeat_count integer not null default 0,
    created_at timestamptz not null default now(),
    constraint uq_dashboard_engagement_participant_session
        unique (participant_id, session_key)
);

create index if not exists idx_dashboard_engagement_participant_id
    on dashboard_engagement_sessions(participant_id);

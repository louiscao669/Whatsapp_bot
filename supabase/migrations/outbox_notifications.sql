-- Cross-surface notification outbox: platform (dashboard) enqueues,
-- message-bot poller drains and pushes messenger notifications.
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

create index if not exists idx_outbox_notifications_participant_id
    on outbox_notifications(participant_id);
create index if not exists idx_outbox_notifications_status
    on outbox_notifications(status);
create index if not exists idx_outbox_notifications_notification_type
    on outbox_notifications(notification_type);
create index if not exists idx_outbox_notifications_created_at
    on outbox_notifications(created_at);

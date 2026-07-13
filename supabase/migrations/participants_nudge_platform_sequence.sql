-- Platform-engagement experiment: per-participant batch-ordinal -> nudge
-- platform sequence (e.g. ABBA/BAAB over 8 batches). Empty list = no
-- experiment assignment; falls back to messenger nudging.
alter table participants
    add column if not exists nudge_platform_sequence jsonb not null default '[]'::jsonb;

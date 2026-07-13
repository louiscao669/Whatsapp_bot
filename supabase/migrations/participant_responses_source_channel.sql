-- Platform-engagement experiment: first-class attribution of which surface
-- produced each answer (user_dashboard | telegram | whatsapp | imessage).
alter table participant_responses
    add column if not exists source_channel text;

create index if not exists idx_participant_responses_source_channel
    on participant_responses(source_channel);

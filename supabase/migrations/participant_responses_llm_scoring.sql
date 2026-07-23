alter table participant_responses
    add column if not exists backtranslated_text text;

alter table participant_responses
    add column if not exists scoring_metadata jsonb not null default '{}'::jsonb;

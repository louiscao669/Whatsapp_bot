-- Audio pronunciations per keyword (multiple takes = alternative readings).

create table if not exists qa_item_keyword_recordings (
    id text primary key default gen_random_uuid()::text,
    qa_item_id text not null references qa_items(id) on delete cascade,
    language text not null,
    keyword_kind text not null,
    keyword_text text not null,
    version int not null default 1,
    storage_uri text not null,
    content_type text,
    uploaded_by text,
    created_at timestamptz not null default now(),
    constraint ck_qa_item_keyword_recordings_kind
        check (keyword_kind in ('required', 'optional')),
    constraint uq_qa_item_keyword_recordings_version
        unique (qa_item_id, language, keyword_kind, keyword_text, version)
);

create index if not exists idx_qa_item_keyword_recordings_qa_item
    on qa_item_keyword_recordings(qa_item_id);

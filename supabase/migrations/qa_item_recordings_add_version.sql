-- Run once on existing databases that created qa_item_recordings without version.
alter table qa_item_recordings add column if not exists version int not null default 1;

with numbered as (
    select
        id,
        row_number() over (
            partition by qa_item_id, recording_type, language
            order by created_at asc, id asc
        ) as version
    from qa_item_recordings
)
update qa_item_recordings r
set version = numbered.version
from numbered
where r.id = numbered.id;

alter table qa_item_recordings
    drop constraint if exists uq_qa_item_recordings_version;

alter table qa_item_recordings
    add constraint uq_qa_item_recordings_version
    unique (qa_item_id, recording_type, language, version);

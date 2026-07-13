-- Canonical identity migration: participants are identified by their own id;
-- every external identity is a participant_provider_contacts row. This drops
-- the legacy participants.wa_id column after backfilling provider contacts.
--
-- Ordering matters: BACKFILL first (reads wa_id), then DROP. Safe to re-run;
-- inserts are guarded by NOT EXISTS + ON CONFLICT, and the drops use IF EXISTS.

-- 1. Telegram: legacy synthetic wa_id was "telegram:<chat_id>". A telegram
--    contact usually already exists; backfill any that are missing.
insert into participant_provider_contacts
    (participant_id, provider, external_user_id, opted_in_at, last_seen_at)
select
    p.id,
    'telegram',
    substring(p.wa_id from 'telegram:(.*)'),
    now(),
    p.last_seen_at
from participants p
where p.wa_id like 'telegram:%'
  and substring(p.wa_id from 'telegram:(.*)') <> ''
  and not exists (
      select 1 from participant_provider_contacts c
      where c.participant_id = p.id and c.provider = 'telegram'
  )
on conflict (provider, external_user_id) do nothing;

-- 2. iMessage: legacy "imessage:<handle>" (if any).
insert into participant_provider_contacts
    (participant_id, provider, external_user_id, opted_in_at, last_seen_at)
select
    p.id,
    'imessage',
    substring(p.wa_id from 'imessage:(.*)'),
    now(),
    p.last_seen_at
from participants p
where p.wa_id like 'imessage:%'
  and substring(p.wa_id from 'imessage:(.*)') <> ''
  and not exists (
      select 1 from participant_provider_contacts c
      where c.participant_id = p.id and c.provider = 'imessage'
  )
on conflict (provider, external_user_id) do nothing;

-- 3. WhatsApp: everything else was a phone number stored directly in wa_id.
insert into participant_provider_contacts
    (participant_id, provider, external_user_id, phone, opted_in_at, last_seen_at)
select
    p.id,
    'whatsapp',
    p.wa_id,
    p.wa_id,
    now(),
    p.last_seen_at
from participants p
where p.wa_id is not null
  and p.wa_id <> ''
  and p.wa_id not like 'telegram:%'
  and p.wa_id not like 'imessage:%'
  and not exists (
      select 1 from participant_provider_contacts c
      where c.participant_id = p.id and c.provider = 'whatsapp'
  )
on conflict (provider, external_user_id) do nothing;

-- 4. Safety check: refuse to drop the column if any participant would be left
--    with no provider contact (i.e. unreachable). Raises if the backfill
--    missed someone; investigate before re-running.
do $$
declare
    orphan_count integer;
begin
    select count(*) into orphan_count
    from participants p
    where not exists (
        select 1 from participant_provider_contacts c
        where c.participant_id = p.id
    );
    if orphan_count > 0 then
        raise exception
            'Aborting wa_id drop: % participant(s) have no provider contact',
            orphan_count;
    end if;
end $$;

-- 5. Drop the legacy column + its index.
drop index if exists idx_participants_wa_id;
alter table participants drop column if exists wa_id;

-- Remove readable platform identifiers from the research database.
--
-- Consent language: no name, telephone number or platform username is stored;
-- the only identifier is keyed and is destroyed with its key at the end of
-- collection. This migration provides the storage for that scheme. It does NOT
-- convert existing rows -- run scripts/migrate_participant_identity.py after
-- applying it, with PARTICIPANT_ID_KEY set, or existing participants become
-- unreachable.
--
-- external_user_id changes MEANING here: it stops being a plaintext chat id and
-- becomes an HMAC blind index. The column type is unchanged so lookups and the
-- unique constraint keep working.

alter table public.participant_provider_contacts
    add column if not exists external_user_secret text;

alter table public.participant_provider_contacts
    add column if not exists identity_key_fingerprint varchar(32);

comment on column public.participant_provider_contacts.external_user_id is
    'HMAC-SHA256 blind index of provider:chat_id. Not reversible. Lookup only.';
comment on column public.participant_provider_contacts.external_user_secret is
    'AES-GCM sealed chat id, base64(nonce||ciphertext). Readable only with PARTICIPANT_ID_KEY, which is never stored in this database.';
comment on column public.participant_provider_contacts.identity_key_fingerprint is
    'Short tag of the key a row was sealed under, so a purge can be verified.';

create index if not exists ix_ppc_identity_key_fingerprint
    on public.participant_provider_contacts (identity_key_fingerprint);

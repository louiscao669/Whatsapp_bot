-- Consent audit trail on participants.
--
-- `participants.consented` was a bare boolean: it recorded THAT consent was
-- given but not when, against which version of the approved form, or whether
-- the person declined. The /pilot consent screen writes all three, so an export
-- can be filtered by form version and a decline is distinguishable from a
-- participant who simply has not reached the screen yet.
--
-- Additive and idempotent. Existing rows keep consented as-is; their
-- consented_at and consent_version stay null, which correctly reads as
-- "consent recorded outside this flow, provenance unknown".

alter table public.participants
    add column if not exists consented_at timestamptz;

alter table public.participants
    add column if not exists consent_version varchar(64);

alter table public.participants
    add column if not exists consent_declined_at timestamptz;

comment on column public.participants.consented_at is
    'When the participant agreed, via the /pilot consent screen. Null for consent recorded out of band.';
comment on column public.participants.consent_version is
    'Identifier of the approved consent text shown (e.g. pilot-2026-08-18).';
comment on column public.participants.consent_declined_at is
    'When the participant declined. A row with consented=false and this set has actively refused.';

create index if not exists ix_participants_consent_version
    on public.participants (consent_version);

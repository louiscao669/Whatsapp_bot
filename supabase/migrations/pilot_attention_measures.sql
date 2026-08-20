-- Companion attention measures for the human pilot, alongside active_time_ms.
--
-- active_time_ms (already shipped) counts time the page was VISIBLE. It cannot
-- see window occlusion, so it is an UPPER bound on reading time. These two add
-- the other side of the bracket:
--
--   focused_time_ms      visible AND the window had focus. Catches "browser on
--                        screen but the participant is in another app"; in
--                        exchange it drops moments when focus went to the
--                        address bar, a browser menu or an OS notification, so
--                        it is a LOWER bound. Focus deliberately does NOT gate
--                        active_time_ms -- a metric that stopped on every
--                        address-bar click would truncate attentive readers.
--
--   passage_onscreen_ms  visible AND the passage element intersected the
--                        viewport (IntersectionObserver, threshold 0). A
--                        different question: was the text on screen, or did
--                        they scroll straight to the answer box?
--
--   focus_change_count   QC covariate, the focus twin of
--                        visibility_change_count.
--
-- Existing rows default to 0, which reads as "not instrumented" -- they were
-- collected before these measures existed and must not be pooled with later
-- rows on these columns. active_time_ms remains comparable across both.

alter table public.pilot_question_trials
    add column if not exists focused_time_ms integer not null default 0,
    add column if not exists passage_onscreen_ms integer not null default 0,
    add column if not exists focus_change_count integer not null default 0;

-- Added via DO blocks rather than "drop constraint; add constraint" so this
-- migration only ever ADDS -- nothing existing is dropped or rewritten, which
-- keeps it safe to apply unattended (see scripts/verify_pilot_readiness.py).
do $$
begin
    if not exists (
        select 1 from pg_constraint where conname = 'ck_pilot_trials_focused_time_ms'
    ) then
        alter table public.pilot_question_trials
            add constraint ck_pilot_trials_focused_time_ms check (focused_time_ms >= 0);
    end if;
    if not exists (
        select 1 from pg_constraint where conname = 'ck_pilot_trials_passage_onscreen_ms'
    ) then
        alter table public.pilot_question_trials
            add constraint ck_pilot_trials_passage_onscreen_ms
            check (passage_onscreen_ms >= 0);
    end if;
end $$;

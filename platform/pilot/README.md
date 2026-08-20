# Human pilot participant interface (`/pilot`)

A deliberately plain study surface: one assigned question at a time, open-text
or MCQ, with the time the question page was **visible** as the primary
measurement. It is a sibling of the user dashboard, not a replacement — the
dashboard is untouched and keeps its rewards, streaks, batches and expiry.

## What it does not do

No rewards, wallet, streak, badge or leaderboard. No correctness feedback while
the study runs. No countdown, no time limit, no expiry. No periodic heartbeat
and no general engagement analytics. No preloading of the next question.

## Running it

From the repository root (`.env` supplies `DATABASE_URL`):

```bash
python platform/app.py
```

Participant URL — the participant id is pseudonymous and is the only credential,
matching the dashboard's convention:

```text
http://127.0.0.1:7860/pilot/<participant_id>
```

A signed deep link works too, and is what a nudge message should contain
(`eten_shared.dashboard_links.build_dashboard_link` produces the token):

```text
http://127.0.0.1:7860/pilot/t/<token>
```

## Where a participant's questions come from

Nothing is hardcoded. `/pilot` serves the participant's existing assignments in
the existing order — the Latin-square plan cell's `sequence_index` first, then
the assignment chain's own order. When the participant has no open assignment
and designed/automatic assignment is enabled, the next one is minted through the
same selector and variant-passage delivery the dashboard uses, so a condition
reaches a participant identically on both surfaces.

Provision participants the usual way before pointing them at `/pilot`:

```bash
python scripts/pilot_import.py --eval-root evaluation   # passages + QA items
python scripts/build_experiment_plan.py --participant-ids id0,id1
python scripts/verify_experiment_delivery.py --language zh
```

Then confirm the whole thing is actually runnable. This checks schema, content,
per-participant plan cells, delivery resolution, runtime flags and leftover
pre-pilot data in one pass, and exits non-zero if anything blocks:

```bash
python scripts/verify_pilot_readiness.py --participant-ids id0,id1
```

`--fix` applies the purely additive repairs and builds missing plan cells. It
will not set `consented`, will not delete anything, will not edit `.env`, and
refuses any migration that drops or rewrites existing schema unless you pass
`--allow-schema-rewrite`.

## Is a participant in the experiment?

A participant is in the grid if and only if they have rows in
`experiment_plan_cells`. Zero cells means `/pilot` falls back to ordinary
coverage assignment and their answers carry no condition. Per answer the marker
is `assignments.experiment_cell_id`; in the export it is the `condition` /
`defect_type` / `defect_rate` columns, which are null for a non-experiment
trial.

## Question progression

`assigned -> started -> submitted`, tracked on `pilot_question_trials.status`.

There is no pilot `expired`. A participant who leaves without answering leaves
the question `started` forever; "incomplete" is derived at report time as
*started with no accepted answer receipt*. The shared `assignments.status`
lifecycle is not touched by the pilot, so the answer-receipt drain and the
messenger surfaces keep working unchanged.

## Timing

Three durations are recorded per question, because no single one is honest on
its own. Each is wrong in a known direction, so together they bracket real
reading time:

| metric | counts while | bias |
|---|---|---|
| `active_time_ms` | page visible | **upper** bound — blind to window occlusion |
| `focused_time_ms` | visible **and** window focused | **lower** bound — address bar, menus and OS notifications steal focus mid-read |
| `passage_onscreen_ms` | visible **and** passage in the viewport | answers a different question: was the text on screen, or scrolled past? |

`active_time_ms` is the primary metric and its definition has not changed:
`document.visibilityState === "visible"`, with `document.hasFocus()` never
allowed to gate it. Focus is *recorded* separately, never used to stop the
primary clock — a metric that paused on every address-bar click would truncate
attentive readers. `passage_onscreen_ms` comes from an `IntersectionObserver`
(threshold 0) scoped to the current question's passage element and torn down
with it, so it cannot become general scroll analytics.

If a conclusion holds under both `active_time_ms` and `focused_time_ms`, the
measurement is not driving it. If they disagree, that is worth knowing before
the full study runs.

Rows collected before these companion measures existed default to 0, which
reads as "not instrumented" — do not pool them with later rows on those two
columns. `active_time_ms` stays comparable across both.

* Durations are measured client-side with `performance.now()` and accumulate in
  closed segments; hidden stretches are never opened.
* `visibilitychange` closes and reopens segments, `pagehide` checkpoints,
  `pageshow` resumes.
* Checkpoints reach the server via `sendBeacon` (falling back to
  `fetch(..., {keepalive: true})`) **only** on those events and at submit —
  never on a schedule.
* Server-side, a checkpoint may only *raise* any duration or counter, so a
  stale beacon, a duplicate unload or a reload can never shrink a measurement.
* Timing stops before the submit request is sent, so neither network nor
  scoring latency is inside `active_time_ms`.

`started_at` (first visible render) and `submitted_at` (`answer_receipts.created_at`)
are both server-generated; `wall_clock_time_ms` is their difference and is a
secondary quality-control metric only.

`sessionStorage` holds only the current question's scratch state — assignment
id, unsubmitted draft, the accumulated durations and counters, current segment
state — and is cleared only after the server acknowledges the submission. Never
a future question, never a score, never a completion state.

## Endpoints

All return `Cache-Control: no-store`; only `/pilot/static/` is cacheable, and
those URLs are version-stamped.

```text
GET  /pilot/api/<participant_id>/question              current question or completion
POST /pilot/api/<participant_id>/session               start/resume, record consent version
POST /pilot/api/<participant_id>/question/viewed       first visible render
POST /pilot/api/<participant_id>/question/checkpoint   visibility/pagehide checkpoint
POST /pilot/api/<participant_id>/answers               submit (idempotent)
GET  /pilot/api/results                                report (admin/expert only)
```

## Results

```bash
python scripts/export_pilot_metrics.py --out-dir evaluation/reports/pilot --include-trials
```

Everything is recomputed from source records at export time; no aggregate is
stored on the participant. Unscored responses are excluded from accuracy
denominators and never counted as wrong — a nonzero `open_unscored` /
`mcq_unscored` means the scoring outbox has not drained yet, so export again
once it has.

## Layout

```text
platform/pilot/
  index.html            page shell
  styles.css
  frontend/
    app.js              rendering + lifecycle (event-driven, no polling)
    api.js              fetch client, all no-store
    timing.js           pure segment timers + sessionStorage store
  tests/timing.test.mjs node --test
platform/app/pilot/
  routes.py             HTTP surface + cache headers
  service.py            study logic
```

Server-side tests live in `platform/tests/test_pilot_service.py`,
`test_pilot_api.py` and `test_pilot_export.py`.

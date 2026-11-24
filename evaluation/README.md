# Evaluation

Evaluation utilities, generated datasets, and local outputs for answer generation
and scoring experiments.

## Mixed Chinese grammar creation

The current **30% misselection / 70% misordering** dose-series builder defaults
to **affected clean-source spans**, replacing whole-clause dose counting. The
first trial of this measurement change is limited to eight 1 Kings 13 windows:

```bash
python3 -u -m evaluation.scripts.pipeline.build_mixed_grammar_ladder
```

It builds 5%, 10%, 15%, 20%, 25% and 30% conditions, within the existing ±2
percentage points. The numerator is the union of countable original characters
in the affected source spans; the denominator is the unchanged clean window's
content-character count. Punctuation and spaces are excluded. The versioned
rule in `grammar_source_spans.py` records every counted span and source position:

- Misordering counts the smallest contiguous reordered block after trimming an
  identical prefix and suffix. Swapping adjacent two-character phrases counts
  their four-character block. Moving a particle counts the block it crosses,
  including the intervening material; this is not minimum moved-token count or
  edit distance. Quoting an unchanged enclosing clause cannot inflate the dose.
- Form substitutions/deletions count disjoint original diff spans. Unchanged
  surrounding and intervening material is excluded.
- Pure insertions use one adjacent clean content character as a source anchor:
  the closest preceding character, or the following one at the beginning.
  For example `请你进来` → `请你的进来` anchors to `你`, counting one source
  character. The anchor is explicitly labelled rather than treated as literally
  replaced text. Duplicate/overlapping positions count only once.

The family mix still counts primary error instances **across the eight windows
at each dose**, not characters. One reviewed candidate per original clause is
retained to avoid combining separately reviewed edits inside one construction.
A dynamic program finds the closest pooled 30/70 ratio among
dose-feasible combinations, then minimizes total dose deviation. It never drops
a feasible window or uses a held candidate to improve the mixture. Ties use a
recorded seed; this is constrained selection, not unrestricted random sampling.
The six doses are selected independently, with no nesting claim.

Explicit user rejections are recorded in `grammar_adjudications.py` and override
cached model approvals during review and candidate selection. On November 23,
2026 the user rejected `驴和狮子都站在尸体旁边。` →
`驴和狮子尸体旁边站在都。` because it introduces a lion-corpse reading,
and `来到米迦的家。` → `米迦的来到家。` because it can change the arriving
participant from the Danites to Micah. These are manual review decisions,
not manually written stimulus text. The
original model judgments remain recorded separately. Matching is on the exact
source/edit pair, not a global ban on mentioning a lion's corpse in other texts.
The current adjudicated 65-window report is
`deliverables/sol_grammar_spans_mix3070_all65_adjudicated.html`; its results and
approved draft package are in
`evaluation/runs/sol_grammar_spans_mix3070_all65_adjudicated_2026-11-23/`.
The earlier model-run reports remain historical records. Apply later explicit
decisions without API calls using `apply_grammar_adjudications --source ...
--output ... --report ...`, always keeping a separate output directory.

Repair held grammar versions with
`python3 -u -m evaluation.scripts.pipeline.repair_mixed_grammar_ladder`.
The default scope is 1 Kings 13, using the adjudicated ladder and the original
first-passage review caches. Previously passing versions remain frozen unless a
new explicit user rejection affects a selected edit. Use `--window-ids` to limit
repair to particular active windows. Prior repair findings are carried forward
so rejected combinations are not retried in a follow-up run. The
initial attempt selects other approved edits; up to two further repair rounds
can replenish at most six misordering proposals per affected window per round
when the bounded search finds no alternative. Existing misselection candidates
remain available and the pooled 30/70 mix is a soft selection preference.
Complete-window risk spans uniquely matching one edit exclude that edit from
repair selection in that window; ambiguous attribution blocks the failed draft
without arbitrarily rejecting an individual edit. Explicit user rejections
remain binding across doses. Failed draft hashes are excluded, so repeated
review cannot turn unchanged failed wording into a pass. Every replacement
receives the existing full-window checks. The separate repair report records
before/after statuses, changed edits, new proposals and all attempts. Unresolved
versions remain held; this command does not publish passages. Use `--offline`
to verify a completed run using exact cached reviews.

The latest combined repair report is
`deliverables/sol_grammar_spans_repair_all65_speech.html`, with derived results and the
approved draft package in `evaluation/runs/sol_grammar_spans_repair_all65_speech_2026-11-23/`.
It combines the completed 1 Kings 13 trial with the separately authorized
remaining-57 run and subsequent focused repairs, preserving their model evidence.
The user rejection of `我对她说：` → `我的对她说：` is recorded in
`grammar_adjudications.py` and applies across doses. A focused repair of
2 Kings 6:29–31 replaced that edit in the 25% and 30% versions; both passed
full-window grammar, source-blind reading and meaning review, at 24.35% and
29.57% actual source-span dose. That repair preserved the other 388 window–dose records.
See `deliverables/sol_grammar_spans_repair_2kgs6_speaker.html` and
`evaluation/runs/sol_grammar_spans_repair_2kgs6_speaker_2026-11-23/` for the exact
changes, user-rejection provenance, model reviews and successful offline replay.
The user subsequently rejected `因为众人说：` → `因为众人话语：` in
2 Chronicles 26:21–23 after the editorial classification hold. That exact pair
is also excluded across doses. Both affected versions were repaired using
existing model-generated alternatives and passed complete-window checks:
25% target at 24.0% actual dose, and 30% target at 28.0%, within the unchanged
±2 percentage-point tolerance. The 388 other records, including the completed
2 Kings repair, remain unchanged. The combined package contains 390 passing
versions and no held versions. The earlier editorial flag and model verdicts
remain in the historical input package; they were not overwritten.
See `deliverables/sol_grammar_spans_repair_2chr26_speech.html` and
`evaluation/runs/sol_grammar_spans_repair_2chr26_speech_2026-11-23/` for this repair.
All of these repair outputs remain unpublished.

Run the established seven local reader settings on the repaired grammar ladder with
`python3 -u -m evaluation.scripts.campaigns.current.run_grammar_ladder_readers all
--passage-id t1_1kgs13 --output evaluation/runs/sol_1kgs13_grammar_readers_2026-11-23
--report-dir evaluation/reports/sol_1kgs13_grammar_readers_2026-11-23`.
This uses the current from-scratch questions and exact approved grammar windows at
5%, 10%, 15%, 20%, 25% and 30%, plus a fresh clean baseline. It validates selected
edits, source-span doses, review verdicts and user rejections before inference.
Model weights, inference options, prompts and choice parsers match the previous
dose experiments. Results retain raw output and available thinking traces; E,
incorrect A–D answers and invalid responses are separate. The established
GPT-4.1-mini mapper receives only unmatched primary-reader answers and choices.
Frozen inputs and per-request checkpoints permit resuming with the `read`, `map`
and `report` stages. No live pilot passages are changed.

The same frozen protocol has also completed `t1_2kgs6_7` (9 active questions,
441 responses) and `t1_2chr26` (6 questions, 294 responses). Their run and report
directories are `sol_2kgs6_7_grammar_readers_2026-11-23` and
`sol_2chr26_grammar_readers_2026-11-23` under `evaluation/runs/` and
`evaluation/reports/`. The held 2 Kings 7:17–18 item remains excluded.
Both runs have no empty or token-limited responses. All 20 E-coded outcomes in
2 Kings were assigned by the established free-text choice mapper; the six E
outcomes in 2 Chronicles were direct parsed responses. Preserve that distinction
when interpreting abstention rather than treating every mapped E as intentional.

`evaluation/reports/sol_three_passage_grammar_readers_2026-11-23/index.html`
compares all three completed passages (1,127 responses) with verified identical
model weights, prompts, source files and inference/scoring settings. Rebuild the
comparison with `evaluation.scripts.campaigns.current.compare_grammar_readers`,
passing the three run directory names to `--runs` and an output report directory
to `--output`. It recounts every summary cell and retains separate passage
denominators (8, 9 and 6); the plotted lines are descriptive, not fitted curves.

The remaining seven passage runs are complete, adding 2,058 responses for 42
questions. The full experiment now covers all 65 active from-scratch questions:
3,185 responses across seven reader settings and seven conditions. The original
three runs (1,127 responses) were preserved byte-for-byte. The combined report is
`evaluation/reports/sol_all65_grammar_readers_2026-11-23/index.html`; reproduce it
without inference using
`python3 -m evaluation.scripts.campaigns.current.report_all_grammar_readers`.
It verifies frozen inputs and model weights, recomputes scores from raw responses,
checks every request's displayed passage, and reports both overall and individual
passage results. All-65 summaries weight questions equally, with 65 responses per
model/condition. Four thinking responses hit the token limit with no final answer
and remain invalid in the denominator. Of 64 E-coded outcomes, 28 were parsed
directly and 36 were assigned by the established free-text mapper. Overall
correctness across the seven readers was 361/455 (79.3%) on clean text and 346/455
(76.0%) at 30%; intermediate doses do not form a monotonic decline. These are
descriptive results from one generation per item/setting, not a significance test.

The isolated local preview at
`evaluation/runs/sol_grammar30_simulation30_2026-11-23/` contains 30 distinct
from-scratch questions spread across all ten passage groups, all at the current
30% grammar target. `preview.py seed` validates the same approved source-span
drafts as the SLM runner, then checks every delivered question on a disposable
database copy. `preview.py serve` starts the local pilot reader; `server.json`
records its URL and port. The reader database starts unanswered at consent,
records responses and timing, and hides test metadata. Its frozen `stimuli.json`
and `participant.json` retain the exact drafts, source hashes, selected IDs and
verified order. This preview does not update the hosted pilot or real assignments.

`--candidate-run` supplies the previous reviewed ladder. Its exact wording and
model/prompt/input-bound reviews are replayed offline, then the source footprints
are calculated separately. If a window lacks an approved combination at a dose,
the writer searches all of its clauses for useful additional misordering edits,
at most six per round and two rounds (`--max-span-extra`, `--span-refill-rounds`).
It stops as soon as every requested dose is feasible; safe source coverage cannot
be manufactured by padding a span or weakening semantic review. The same
mechanical, grammar, source-blind and semantic checks apply. Every newly assembled
version receives complete-window review (or an exact cache match). Only
passing complete versions enter `approved_window_drafts.json`. There is no
publication or silent replacement of live grammar passages. `--offline` replays
the completed run without API calls. See
`deliverables/sol_grammar_spans_mix3070_1kgs13_5_to_30.html` for all versions, actual
doses, selected family counts, and review findings, including ratios restricted
to passing versions and the exact counted spans. Raw results and review caches
are in `evaluation/runs/sol_grammar_spans_mix3070_1kgs13_5_to_30_2026-11-23/`.

The earlier whole-clause 1 Kings 13, remaining-57 and combined-65 results remain
archived under their original `sol_grammar_mix3070_*` paths. They are not silently
relabelled or regenerated. The combined historical report is
`deliverables/sol_grammar_mix3070_all65_5_to_30.html`. `--dose-basis whole_clause`
retains the old calculation for a separately named comparison run. Expanding
the revised source-span workflow beyond the first passage requires new user
authorization; the prior full-bank run used the different whole-clause measure.

The original `build_mixed_grammar_windows` candidate-bank workflow adds three misselection classes
to the existing misordering candidates:

- `word_form`: related word forms or grammatical constructions, including
  possessives and noun/verb/adjective/adverb mismatches. A grammatical marker can
  be added or removed, but substantive information cannot be added or omitted.
- `classifier_selection`: an incompatible classifier with the same intended
  noun, number and counting unit. Changing an individual count to a container
  count is a semantic change and cannot pass as grammar alone.
- `verb_aspect_construction`: an incompatible verb/aspect construction while the
  action and intended temporal/aspectual meaning remain recoverable.

There is no separate structural-particle-selection class. Simple 的/地/得
substitutions are excluded. Valid Chinese ellipsis or flexible word-class uses
are not automatically errors. Actual character substitutions, additions and
deletions are recorded separately from linguistic categories. Existing marker
misplacement is allowed under misordering and is not itself lexical damage.

```bash
python3 -u -m evaluation.scripts.pipeline.build_mixed_grammar_windows
```

The default trial uses only the eight **1 Kings 13** windows, with the configured
`gpt-6.1-sol` writer and independent reviewer. The base writer proposes at most
two candidates per misselection class per window. A separate mandatory writer
search proposes up to two additional **lexical word-class** candidates per window
(`--max-word-class`). Marker-only proposals cannot fill these additional slots;
unavailable classes or lexical opportunities get explicit reasons.
Existing misordering candidates are reviewed again under the new rubric. No
questions, answer keys or participant data are sent. New candidate wording comes
from the writer, not hand-written replacement entries.

The lexical search inspects nouns, verbs, adjectives and adverbs and returns an
exact source form, related replacement form, and both claimed word classes in
context. A separate reviewer must confirm that this creates an actual class
incompatibility. Ordinary Chinese conversion, uncommon but grammatical wording,
an invented suffix, and changes to the underlying concept cannot pass merely
because a writer labelled them a word-class error. Possessive and construction
marker errors remain supported through the base writer. The new stage prevents
all word-form search slots from being consumed by 的 insertion.

Each candidate receives mechanical protection checks, a grammar/category review,
a source-blind reading, and a semantic comparison. The assembled window then
receives grammar and semantic reviews for interactions between edits:

- **Pass**: conspicuously ungrammatical, underlying meaning recoverable.
- **Flagged**: a credible new ambiguity, uncertainty, or reviewer disagreement.
- **Needs repair**: ineffective grammar, invalid edit, altered/lost substantive
  meaning, unrecoverable meaning, or no passing combination within the dose.

Only passing candidates can be selected; only passing complete windows enter
`approved_window_drafts.json`. Flagged and failed material stays in the report.
There is no automatic repair reroll or publication in this creation trial.

The default target is 30%, within 2 percentage points, measured as **clean
content characters in the affected whole clauses / clean window characters**.
Replacement length does not change that denominator. The mixture counts selected
primary error instances; it does not count affected characters. No fixed family
ratio is imposed by default: selection favors type diversity within the dose,
then seeks coverage of passing lexical word-class proposals. It never uses a
held proposal or exceeds the dose to achieve that coverage.
`--misselection-share 0.7` is an optional soft preference, never a reason to exceed
the dose or use a held candidate. A different experiment needs its own output
folder and report. Seeds make selection repeatable for the same candidate bank.

Results and exact model/prompt/input-bound caches default to
`evaluation/runs/sol_mixed_grammar_word_class_1kgs13_2026-11-22/`; the review page is
`deliverables/sol_mixed_grammar_word_class_1kgs13.html`. Re-run the same command to resume
valid caches, or add `--offline` to verify/rebuild from cached evidence without
API calls. Changed source text or pipeline inputs require a separate run folder.
This extension does not rewrite or relabel the existing structural grammar bank
or change live participant passages.

To reuse the first trial's unchanged base proposals and reviews while running
the new lexical search, use:

```bash
python3 -u -m evaluation.scripts.pipeline.build_mixed_grammar_windows \
  --reuse-cache-from evaluation/runs/sol_mixed_grammar_1kgs13_2026-11-22
```

Reuse copies raw records to the new run. Every cache lookup still checks its
exact model, prompt, schema and input binding; a saved pass status alone is never
reused as evidence. Conflicting records are not overwritten. The first trial's
results and report remain available in their original locations.

The November 22 first trial produced 15 word-form, 11 classifier-selection and
11 verb–aspect candidates, and re-reviewed 24 existing misordering candidates.
All 61 passed the configured model reviews. All eight assembled windows passed,
at 29.07–30.34% affected-clause coverage. Offline replay reproduced the results.
These are reviewer decisions, not human-study outcomes. In this trial all 15
word-form proposals inserted 的; wider noun/verb/adjective/adverb form variety
is allowed by the rules but has not been demonstrated by this batch. No fixed
misselection/misordering proportion was imposed and no drafts were published.

The follow-up lexical search on the same eight windows proposed six candidates:
four passed, one was flagged, and one needed repair. The four approvals use two
verb-to-noun patterns, 回答 → 答案 and 呼喊 → 呼声, each in two contexts.
裂开 → 裂痕 was flagged because a mere crack may weaken the original event;
愿意 → 意愿 needed repair because the blind reader did not find an obvious
grammar violation. Three assembled drafts changed (13:1–3, 13:8–10, 13:11–14);
all eight complete-window reviews passed, with both held candidates excluded.
The other three windows received explicit no-opportunity explanations from the
lexical writer. These results demonstrate lexical substitutions beyond 的, but
not yet every adjective/noun/verb/adverb direction. The run reused all unchanged
base model records; 35 new structured replies covered the lexical search and
its reviews. Offline replay and 170 targeted tests passed. Nothing was published.

The subsequently authorized remaining-passage run processed 57 additional active
windows in nine passage groups, carrying forward the eight 1 Kings results from
cache. Of the 57, **55 passed**, **1 was flagged** (2 Chronicles 26:11–15, possible
aspect ambiguity from 统领了着), and **1 needs repair** (Acts 23:25–26, no whole-clause
combination meets the 30% ±2pp dose). Across all 65 windows, 63 passed. Remaining-set
candidate reviews: 425 pass, 6 flagged, 10 need repair, including re-reviewed
existing misordering candidates. The dedicated lexical search subset had 42
passes, 1 flag and 6 repair needs. These are model review decisions, not human
validation or publication.

The full-bank preflight exposed one legacy partial-clause record in Acts 23:25.
The importer now expands its review focus to the exact enclosing clean clause,
preserving the displayed edit and the original record in provenance. Its dose
counts the full 9-character clause, not the old 7-character fragment. The short
window has clauses of 2, 9 and 14 characters (25 total); no combination supplies
the 7–8 characters required by the target interval. This is held rather than
silently changing the whole-clause dose rule.

One separate technical candidate hold remains in Acts 19:11–12: the inherited
name map treats 神借着 as a protected entry, so the guard rejects a rearrangement
even though 神 remains intact. The compact report explicitly identifies this
over-broad guard. The raw candidate remains held; its status was not manually
promoted, and its window passed using other edits.

Final run: `evaluation/runs/sol_mixed_grammar_all65_clause_bounds_2026-11-22/`.
Summary: `deliverables/sol_mixed_grammar_remaining57.html`; all candidates and
windows: `deliverables/sol_mixed_grammar_all65.html`. `remaining57_summary.json`
and `full_bank_verification.json` bind the summary to the final results. The
earlier `sol_mixed_grammar_all65_2026-11-22/` folder is an interrupted attempt used
only as a source of valid caches. The final run passed offline replay, exact
reconstruction and decision checks, with 172 targeted tests passing after the
import fix. No live passages or participant plans were changed.

## Development run scope

As requested on November 18, 2026, develop and revise pipelines using **one
Bible passage first**, including only its associated QA windows. Keep that
passage fixed across iterations, inspect the results, and finalize the workflow
with the user before an authorized full-bank run. Local checks without model
calls may still cover the full dataset. See [evaluation instructions](AGENTS.md).

## Full Pipeline

Run from the repository root with a canonical Chinese passage and the original
English QA set:

```bash
export OPENAI_API_KEY=...
python evaluation/main.py \
  evaluation/datasets/passages/luke_ch1_zh_passage.txt \
  path/to/qa_original_english.json \
  --run-name luke_ch1
```


for ch in {2..8}; do
    qa="evaluation/datasets/qa/qa_output_luke_ch${ch}_all_formats.json"

    python evaluation/main.py \
      "evaluation/datasets/passages/test_passage_luke${ch}.txt" \
      "$qa" \
      --output-dir "evaluation/outputs/luke${ch}/nllb_dropout_gradient" \
      --run-name "luke_ch${ch}_all_formats" \
      --methods \
        nllb-200-1.3B-dropout-0.0 \
        nllb-200-1.3B-dropout-0.1 \
        nllb-200-1.3B-dropout-0.2 \
        nllb-200-1.3B-dropout-0.3 \
        nllb-200-1.3B-dropout-0.5 \
        nllb-200-1.3B-dropout-0.7 \
        nllb-200-1.3B-dropout-0.9 \
      --answer-provider ollama \
      --answer-model qwen3:1.7b \
      --ollama-no-think \
      --allow-partial-answers \
      --continue-on-method-error
done

The pipeline:

1. Translates QA questions to Chinese. Open standard answers stay English; MCQ
   options are translated because they are part of the displayed question.
2. Replaces canonical English source terms with protected tokens such as
   `__PERSON_C__` before passage translation.
3. Converts protected tokens in the translated passage to Chinese placeholders
   and decanonicalizes the translated QA set and any remaining translated
   passage aliases as a fallback.
4. Uses the configured answer model to answer the decanonicalized Chinese
   questions from local verse windows of the decanonicalized Chinese passage.
5. Back-translates generated open answers to English.
6. Scores against the original English QA set.

Each stage reuses its existing output file unless the file is missing or you
pass `--force` / `--force-translate` / `--force-answer` /
`--force-decanonicalize` / `--force-backtranslate` / `--force-score`.

For the local 1B Ollama answer model, keep the default `--answer-verse-window 2`
so each answer call receives the referenced verse plus two verses before and
after it:

```bash
python evaluation/main.py \
  evaluation/datasets/passages/test_passage_luke1.txt \
  evaluation/datasets/qa/qa_output_luke_ch1_mixed.json \
  --answer-provider ollama \
  --answer-model llama3.2:3b \
  --force-answer
```

## Compare clean Chinese passage translations

The November 9 comparison uses the original high-quality passage prompt with
`gpt-6.1-sol`. `gpt-6-astra` compares the two Chinese texts against the English
in both anonymous presentation orders. Run these modules from the repository
root. Model requests, responses, model IDs, and reviews are saved under
`evaluation/runs/clean_passage_sol_astra_2026-11-09`.

```bash
python3 -m evaluation.scripts.pipeline.compare_clean_passages translate
python3 -m evaluation.scripts.pipeline.compare_clean_passages review
```

Inspect the two diagnostic verses and the complete passage reviews before
recording a decision. Supply exact Chinese quotations for the ambush target at
Judges 9:25 and the shouted announcement at 2 Kings 7:11. For the saved run:

```bash
python3 -m evaluation.scripts.pipeline.compare_clean_passages decide \
  --ambush-evidence 要对付亚比米勒 --shouting-evidence 高声传报
python3 -m evaluation.scripts.pipeline.compare_clean_passages translate --remaining
python3 -m evaluation.scripts.pipeline.compare_clean_passages review --remaining
python3 -m evaluation.scripts.pipeline.compare_clean_passages finalize --all
```

`prepare_clean_passage_conditions base` rebuilds the omission levels and checks
the word-by-word source. Run that module with `grammar` for reviewed 30% grammar
edits. The release uses Astra to propose grammar edits for the six-verse Acts 20
passage after Sol fell short of the requested coverage. The grammar and meaning
checks use the same settings across all ten passages.

The grammar reviewer uses `recoverable_meaning_semantic_risk_v3`: processing
difficulty and rereading do not fail an otherwise faithful edit. Newly plausible
competing meanings and unresolved reviewer disagreement are flagged; confirmed
meaning changes, unrecoverable semantics, broken lexical words, and ineffective
grammar edits need repair. Only a pass is eligible for automatic acceptance.
Archived v1/v2 reviews retain their original policy and are not promoted to v3.
To review the existing 24 Grammar 30% edits in the eight 1 Kings 13 windows, run
`python3 -m evaluation.scripts.pipeline.review_grammar_windows`. This reviews
each edit in the exact displayed context and separately compares each complete
window. It sends passage text only, saves resumable model evidence, and produces
`deliverables/sol_1kgs13_grammar_semantic_risk.html`; it does not rewrite or publish
passages. Add `--offline` to rebuild the report from matching cached reviews.
After approval to expand, `--all-active` checks all 65 active windows and 184
selected grammar edits, excluding the held officer question. For the November
22 full review, use `--all-active --workers 8 --reuse-from
evaluation/runs/sol_1kgs13_grammar_semantic_risk_2026-11-22`. Reused evidence must
match the source, model, policy and exact request and passes an offline replay
before any new requests. The all-window report is
`deliverables/sol_all65_grammar_semantic_risk.html`, with a status filter and
separate individual-edit, combined-window and overall-window results.

For mistranslation, generate the usual length-scaled, independently judged
`mistranslation_bank_sol_length_zh.json` banks against the run's `release` root,
then use `prepare_clean_passage_conditions mistranslation` to extend coverage
and render the nested doses. All three actions use
`python3 -m evaluation.scripts.pipeline.prepare_clean_passage_conditions`.

`check_clean_passage_questions` checks the saved Chinese MCQs on the new windows
using local Ollama. `verify_clean_passage_release` reconstructs every condition,
checks dose and window coverage, and publishes the immutable local passage pack
under `evaluation/datasets/passages/tier1_zh_sol_v1_2026-11-09/`. Both are
modules under `evaluation.scripts.pipeline`. Database import and participant
assignment are separate operations.

### Generate the pilot defects per QA window

Run the window generator from the repository root for the eligible from-scratch
Sol questions. It selects edits from the existing omission units and reviewed
grammar and mistranslation banks, then applies the passage generators and verifies
the rendered wording against the edits inside each window.

```bash
python3 -m evaluation.scripts.pipeline.build_prepared_window_conditions \
  --bank from-scratch \
  --output evaluation/runs/sol_scratch66_window_doses_2026-11-14/conditions.json \
  --report evaluation/reports/sol_scratch66_window_doses_2026-11-14/windows.html
```

The target percentages come from the pilot slots. The denominator is the
clean content-character count in the question's exact verses. Grammar counts
the entire edited clause. The 30% selection includes the 15% edits within each
two-dose family. The report lists the achieved rate for each condition and
flags results outside the release tolerance. The JSON keeps both the generated
wording and the original edit spans for review. Both outputs are local drafts.

For windows held on grammar or mistranslation, the following run invokes the
configured writers and independent reviewers on the clean verses. Response
caches are scoped to each window and family. The refit combines accepted edits
with the original candidates, preserves passing lower doses, and rejects
overlapping substitutions. Each acquisition round is recorded locally.

```bash
window_run=evaluation/runs/sol_scratch66_window_doses_2026-11-14
python3 -m evaluation.scripts.pipeline.refill_window_defects --draft "$window_run/conditions.json" --root "$window_run/refill_v3" --passage-id t1_1kgs13
python3 -m evaluation.scripts.pipeline.refit_window_doses --draft "$window_run/conditions.json" --root "$window_run/refill_v3" \
  --output "$window_run/refilled_v3.json" --report evaluation/reports/sol_scratch66_window_doses_2026-11-14/refilled_v3.html
```

The November 18 mistranslation refill uses **schema-3 occurrence-anchored bundles**.
Use a fresh output root; historical schema-2 banks remain readable and are not
silently converted. Candidates target exact source occurrences, may compete for
the same spans, and may contain 1–4 coordinated substitutions. A bundle is
reviewed and selected as one unit. Longer meaning-bearing spans are allowed;
unchanged context must not be used to inflate the dose. Identical prefixes and
suffixes are mechanically removed from proposed substitution spans before review
and counting, while retaining a nonempty anchor for polarity reversals. The
rendered wording must be identical before and after this normalization. The dose
still counts the selected source-span content characters; historical banks are
not rewritten or recounted.

The default acquisition bound is **60 total proposals per window**, including
duplicates and rejected proposals, in **at most five batches of 12**. Every
candidate needs an independent review. Each batch allows at most three reviews
of complete selections. Acquisition stops early only when a reviewed selection
reaches the requested coverage (default 60%); numeric coverage alone is not a
success. Partial banks retain their actual coverage, verdicts, and stop reason.
When a reviewer rejects and quotes a specific broken phrase, the selector
retains a constraint against the contributing bundles appearing together.
Unrelated edits cannot clear that earlier local fluency failure. Failure memory
is tied to the exact source, substitutions, and reviewer request and reused when
resuming the same window.
No new bank is published to the live pilot by these commands.

While developing this workflow, use one passage, or an individual window within
that passage. For the first high-coverage trial:

```bash
python3 -m evaluation.scripts.pipeline.refill_window_defects \
  --draft evaluation/runs/sol_scratch66_window_doses_2026-11-14/matched_clauses.json \
  --root evaluation/runs/sol_mistranslation_bundles_2026-11-18 \
  --passage-id t1_1kgs13 --window-start 13:6 \
  --families mistranslation --expand-mistranslation --workers 1 \
  --mistranslation-target 0.60 --max-candidates 60 --batch-size 12 --max-batches 5
```

`--expand-mistranslation` also processes windows that already meet the old study
doses. The target here is bank capacity, not a change to participant conditions.
`--all-passages` requires explicit authorization for the larger run. Rerunning
identical requests reuses cached proposals and judgments. Changed bounds need
a fresh output root; compatible response caches can be copied into it.

When schema-3 candidates enter `refit_window_doses` or `match_window_defects`, the
selected complete window receives a mandatory review, including any combined
legacy edits. Failed or uncertain wording is held even when its dose fits.
Contradictions and unclear references can pass with recorded flags. The legacy
passage publisher cannot bypass this window review for schema-3 banks.

For the from-scratch human pilot, fit the reviewed edits jointly to favor the
same clauses across defect types at each dose. Run this once before assigning
the resulting passages to readers.

```bash
python3 -m evaluation.scripts.pipeline.match_window_defects --draft "$window_run/refilled_v3.json" \
  --root "$window_run/refill_v3" --seed 20261114 --output "$window_run/matched_clauses_v3.json" \
  --report evaluation/reports/sol_scratch66_window_doses_2026-11-14/matched_clauses_v3.html
```

The fit preserves dose bands, nesting, the boundaries of each verse and
within-family edit compatibility. It first prefers identical clause sets in
full comparisons, then in comparisons among the remaining in-band variants.
When full matching is infeasible it prefers at least one shared clause,
then agreement on the marked answer-evidence phrases, then fewer differing
clauses. Seeded random weights break remaining ties; they do not give every
tied combination an equal probability. The run also checks each dose for
exact-match feasibility independently, with both nested ladders in place.

`evaluation/datasets/perturbations/sol_scratch66_answer_evidence.json`
records the clean quotations used for each current stem and key. The report
lists the selected clauses, source-character doses and evidence touches.
A grammar edit counts its reviewed source clause even when only some words
move. Re-running this command creates a local draft.

For comparison with the earlier omission-only design, this optional command
draws omission locations against fixed grammar and mistranslation variants.

```bash
python3 -m evaluation.scripts.pipeline.draw_window_omissions --draft "$window_run/refilled.json" \
  --policy least-overlap --seed 20261114 --output "$window_run/omissions_least_overlap.json" \
  --report evaluation/reports/sol_scratch66_window_doses_2026-11-14/omission_overlap.html
```

The stage enumerates whole-clause 30% omission sets that preserve some content
in every verse and admit a valid nested 15% set. Under `uniform`, each eligible
30% set has the same chance, followed by an equal draw among its valid 15%
subsets. Under `least-overlap`, the high-dose draw is among sets sharing the
fewest distinct clauses with the passing 30% grammar and mistranslation edits.
The low-dose draw then minimizes overlap with passing 15% mistranslation within
the selected 30% set. Ties are drawn with the recorded seed. If the window has
no valid pair, its existing wording and review statuses are retained. The
audit reports shared clauses, including a clause where a replacement touches
only part of the omitted text. The draws use the same passages for all readers
assigned to a given question and condition when that draft is used.

### Generate word and phrase omission candidates

The automatic candidate stage uses the 66 frozen from-scratch windows, paired
English source and clean Chinese only. It proposes up to four independent
deletions per window at each requested level with the configured writer and
reviews the exact resulting text with the independent reviewer.

```bash
python3 -m evaluation.scripts.pipeline.build_omission_phrase_bank --automatic --unit word
python3 -m evaluation.scripts.pipeline.build_omission_phrase_bank --automatic --unit phrase
```

Word level means one source lexical item, not one Chinese character. Necessary
grammatical padding and compound names or numbers do not change that level.
Currency and measurement units such as shekels or years are meaningful content,
not grammatical padding; removing the number and its unit together is a phrase
omission. Lexical size alone does not establish study eligibility.

Word omissions must remove key passage information: a person/group identity,
a specific place, or a significant relationship (e.g. kinship, ownership,
allegiance or who acted toward whom). The reviewer must identify the concrete
gap in the displayed narrative, without seeing or targeting the QA answer.
Minor attributes, quantity changes and markers alone are insufficient.
Standalone 忽然, 就, 不, 因此 and similar markers are excluded even if deleting
them changes meaning, chronology, causal logic or polarity. Exact whole-marker
matches (allowing surrounding punctuation) are rejected before model review;
this is never a substring ban on a name containing the same characters.
Other candidates receive an independent key-content classification and reason.
Thus a negation deletion can remove information yet still be ineligible.
Exact deletion-only compliance is verified by source-span reconstruction;
the review retains the model's raw checks and any recorded enforcement overrides.
Phrase level means a meaningful constituent
larger than one lexical item and smaller than a complete predication.

Acceptance requires `yes` for information omitted, fluency, deletion only,
valid omission unit, and validity in the displayed context. A `no` or
`uncertain` required check rejects the candidate. Word-level review additionally
requires `key_content_removed=yes` and an eligible person/group, place, or
significant-relationship category: six required checks in total. Uncertainty
about significance causes rejection. Additional semantic distortion
from deletion is recorded as `other_meaning_changed` or
`possible_other_meaning_changed`, without overriding these required checks.
Ambiguous references and information recoverable elsewhere are separate flags.

The word bank is saved as `sol_scratch66_omission_word_bank_auto_v6.json`
and the phrase bank as `sol_scratch66_omission_phrase_bank_auto_v4.json` under
`evaluation/datasets/perturbations/`. The corresponding full review reports are
`deliverables/sol_scratch66_omission_words_auto_v6.html` and
`deliverables/sol_scratch66_omission_phrases_auto_v4.html`. Re-running reuses
receipts keyed by the actual model, prompt, input and response schema; word and
phrase requests have distinct prompts. An optional `--prior-bank` re-reviews
earlier candidates of the same unit and frozen window release. Add
`--review-only` to assess that exact prior pool without requesting new
proposals. Save the new bank separately to preserve the old decisions. For
example, to recheck the version 5 word bank under the version 6 criteria:

```bash
python3 -m evaluation.scripts.pipeline.build_omission_phrase_bank --automatic --unit word \
  --review-only --prior-bank evaluation/datasets/perturbations/sol_scratch66_omission_word_bank_auto_v5.json
```

Without a prior bank, only fresh proposals count. These are candidate banks, not selected 15%/30% passage
variants; combinations require a further contextual review.

### Review existing clause omission candidates

```bash
python3 -m evaluation.scripts.pipeline.review_omission_clauses
```

This stage enumerates every unit produced by the existing omission splitter
inside the 66 frozen windows, including units already used at 15% and 30%.
Punctuation segmentation does not certify a linguistic clause or its importance.
The current audit (review version 8) treats word/phrase/clause size as classification
metadata, not an acceptance gate. A candidate can be a valid omission even when
it belongs in a different size category. Use the recorded `unit_kind` for later
mixture accounting; do not count every accepted splitter unit as a clause.

Before review, deterministic boundary repairs preserve opening/closing quotes
and retain the existing terminal punctuation when deleting a final conjunct.
They change only the deletion boundary, never insert or substitute text. The
removed lexical sequence and content-character dose must stay identical.
For example, delete `，也必在你上面焚烧人的骨头` and retain the period, instead of
deleting `也必在你上面焚烧人的骨头。` and leaving a dangling comma. Original spans
are retained for provenance and comparison with currently selected edits.
If a proposed repair fails, the reviewer also evaluates the original deletion
boundaries without seeing the failed verdict. Prefer a passing alternative;
otherwise retain an uncertain alternative for review before a definite rejection.
Both attempts are recorded. This prevents a retained period from unnecessarily
turning a surviving time phrase into a sentence fragment when the original comma
would have joined it naturally to the next sentence.

The configured reviewer reads the full paired window and each exact edited
verse. It receives no QA content, current selection labels, or earlier verdicts.
It may cite multiple separated English spans, including other displayed verses.
Missing or uncertain narrow alignment is a nonblocking flag, not a rejection or
an excuse to skip semantic review. English quotations are mechanically checked;
unverified quotations are flagged and never highlighted as verified evidence.

The five required checks are information omitted, fluency, deletion only,
validity in context, and key content removed. Concrete events, actors, places,
outcomes, instructions, conditions and relationships need not be central to the
entire plot. Standalone markers, emphasis-only changes and removals without
substantive content remain excluded. Recoverability elsewhere and additional
semantic distortion are nonblocking flags. A definite failed required check
rejects; unresolved required-check uncertainty is held for review. Pure deletion
is mechanically verified. Empty-verse candidates are held separately under the
existing preserve-verse design constraint, not called invalid omissions.

Outputs are `evaluation/datasets/perturbations/sol_scratch66_omission_clause_bank_auto_v2.json`
and `deliverables/sol_scratch66_omission_clauses_auto_v2.html`. Version 1 is retained
and used only for local before/after comparisons. The report shows classifications,
boundary repairs, current selected units, and selected phrase exceptions outside
this audit. Individual acceptance does not validate combinations of edits; final
dose passages still need fitting and contextual review. This command does not
modify the released manifest, participant assignments, or hosted database.

### Re-review existing phrase candidates

Start with one Bible passage while refining the checks. This command reviews
only the existing 1 Kings 13 candidates, saves passage-specific outputs, and
leaves the full-bank results and released passages unchanged:

```bash
python3 -m evaluation.scripts.pipeline.review_existing_omission_phrases \
  --passage-id t1_1kgs13 --workers 2
```

After the workflow is finalized and a full-bank run is authorized:

```bash
python3 -m evaluation.scripts.pipeline.build_omission_phrase_bank --automatic --unit phrase \
  --prior-bank evaluation/datasets/perturbations/sol_scratch66_omission_phrase_bank_auto_v4.json \
  --review-only
```

This review-only path now uses `review_existing_omission_phrases` and the same
five-check policy as the revised clause audit. It rechecks all 189 existing
proposals in the v4 bank, including previous rejections, without requesting new
proposals. All 66 window records are preserved, including the window with no
existing candidates. Chinese deletion locations, clean-window hashes, English
source hashes and the roster are validated before model calls. A missing or
inexact earlier English quotation does not prevent full-window semantic review.

The configured reviewer receives the paired window and each exact deletion,
without QAs, earlier verdicts, earlier alignment quotations, or selection labels.
Required checks are information omitted, relevant content removed, fluency,
deletion only, and validity in context. Unit classification and narrow alignment
are metadata, not vetoes. Secondary semantic distortion and recoverability are
nonblocking flags. Definite substantive failures reject; unresolved substantive
uncertainty is held. Boundary repairs and original-boundary fallbacks share the
clause implementation and preserve the removed lexical sequence and its dose.

Outputs are `evaluation/datasets/perturbations/sol_scratch66_omission_phrase_bank_auto_v5.json`
and `deliverables/sol_scratch66_omission_phrases_auto_v5.html`. The bank records the
original proposals, previous decisions, provenance hashes and reviewed unit
classifications. The report separates pass, pass with flags, held, and rejected.
The stored acceptance state remains `accepted` for both passing groups; the
four-way display outcome is separately recorded as `review_outcome`. Use the
reviewed `unit_kind` for later mixture accounting, rather than assuming every
candidate in this bank is a phrase. Word-bank reviews keep their existing route.
This command does not regenerate combined dose passages or publish to the pilot.

### Trial a 20/40/40 omission mixture on one passage

Use the reviewed word, phrase and clause banks together. This trial is scoped to
one passage; the percentages describe deletion occurrences across its windows,
separately for the 15% and 30% character doses. First fit locally, then review the
complete combined passages:

```bash
python3 -m evaluation.scripts.pipeline.build_mixed_window_omissions --passage-id t1_1kgs13
python3 -m evaluation.scripts.pipeline.build_mixed_window_omissions --passage-id t1_1kgs13 --review --max-rounds 2
```

Dose bands (±2 percentage points), nested low/high selections, nonoverlapping
spans and nonempty verses are hard constraints. The fitter checks exact mixture
feasibility, then minimizes absolute event-count deviation from 20/40/40 at each
dose. It next favors overlap with the fixed grammar/mistranslation clause
locations, then dose centers, with seeded tie-breaking. This is not a uniform
random draw or a claim to minimize percentage-point error. Word events must pass
the dedicated word bank's stricter eligibility checks. Accepted phrase/clause
candidates use their reviewed classifications; duplicate or overlapping spans
cannot inflate the counts. Conflicting duplicate reviews are excluded.

The combined-window reviewer sees paired English, clean Chinese, exact rendered
variants and deletion spans, without QAs or previous verdicts. It checks actual
information loss, substantive content, fluency, deletion only and validity in
context. Additional semantic distortion and recoverability are flags. Failed
combinations receive at most one new selection; passing combinations stay fixed.
Only punctuation may be cleaned up automatically, without changing lexical
content or dose. Any failures remaining after the trial stay visible for review.

Outputs are under `evaluation/runs/sol_omission_mix_204040_2026-11-18/<passage-id>/`
and `deliverables/sol_omission_mix_204040_<passage-id>.html`. These drafts do not
modify the released manifest, participant assignments or hosted data.

### Rebuild the 5–60% omission ladder with the published comparisons fixed

The November 21 rebuild covers the 65 active windows at 5, 10, 15, 20, 25,
30, 40, 50 and 60 percent. It uses a **20/50/30 word/phrase/clause preference**
by deletion occurrences pooled separately at each dose. The published 15% and
30% variants are immutable. The 40%, 50% and 60% versions retain every deletion
from the preceding level, starting at the published 30%. The other doses are
selected independently.

```bash
python3 -u -m evaluation.scripts.pipeline.rebuild_omission_ladder \
  --output evaluation/runs/sol_omission_mix205030_all65_5_to_60_2026-11-21/mixture.json \
  --report deliverables/sol_omission_mix205030_all65_5_to_60.html
# After inspecting the local selection, run/resume the authorized model review:
python3 -u -m evaluation.scripts.pipeline.rebuild_omission_ladder \
  --output evaluation/runs/sol_omission_mix205030_all65_5_to_60_2026-11-21/mixture.json \
  --report deliverables/sol_omission_mix205030_all65_5_to_60.html --review
```

The run checks input hashes, reuses only identical complete-context reviews,
and allows at most three selection/review rounds and two batches of eight new
candidates per window. Every new candidate and combined passage must pass the
existing bilingual checks. Out-of-band variants remain held, even if their
language review passes. The mixture is a preference; its achieved proportions
are reported for all selections and separately for passing variants. Solver
timeouts retain only solutions verified against every constraint, and the
fallback stages are recorded without claiming optimality.

After repairs, the selector may retain previously reviewed 40/50/60% versions
when they form a valid nested sequence and increase passing coverage. It does
not edit their wording or override any exact-context failed review. The original
final-round cells and source rounds are preserved in `reviewed_chain_retention`.

`verification.json` checks all 585 variants, exact replay, the 130 unchanged
published comparisons and all 65 nested high-dose ladders. These outputs are
local drafts: the command does not publish passages or modify participant data.

The approved November 22 research release is
`evaluation/datasets/passages/sol_scratch65_omission_205030_ladder_v1.json`.
It contains 551 approved variants; the 34 held variants appear only as exclusion
metadata. `python3 -m evaluation.scripts.pipeline.release_omission_ladder` rebuilds
that immutable package from the completed review. Hosted publication uses
`human_pilot/pilot_publish_omission_ladder.py` in a separate research namespace;
it does not add conditions to the human pilot.

Rerun the original seven small-model settings with:

```bash
python3 -u -m evaluation.scripts.campaigns.current.rerun_omission_ladder all
python3 -m evaluation.scripts.campaigns.current.report_omission_ladder_rerun
```

The reader campaign checkpoints each response and reuses only identical prior
requests with identical model weights. It covers 4,312 responses: 551 omission
variants plus 65 clean baselines, each with seven reader settings. Of these,
1,092 requests are unchanged and 3,220 require new inference. The original
GPT-4.1-mini choice mapper handles unmatched primary-reader answers only.
Accuracy against the clean key, wrong A–D responses, E and invalid outputs are
separate. Main before/after graphs use the same 42 questions at every dose;
all available per-dose results and denominators are retained. Reports are under
`evaluation/reports/sol_omission205030_readers_2026-11-22/`.

### Nested 30/40/50/60 window trial

Build both omission and mistranslation ladders on one passage while developing
the workflow:

```bash
python3 -u -m evaluation.scripts.pipeline.build_nested_window_defects \
  --passage-id t1_1kgs13 \
  --output evaluation/runs/sol_nested_defects_2026-11-18/t1_1kgs13
python3 -m evaluation.scripts.pipeline.report_nested_window_defects \
  evaluation/runs/sol_nested_defects_2026-11-18/t1_1kgs13/nested.json \
  deliverables/sol_nested_defects_1kgs13.html
```

The selector fits all four levels jointly. Earlier deletion spans remain deleted;
earlier substitution spans retain exactly the same replacement. Coordinated
candidate bundles are atomic. Overlaps cannot inflate coverage, and each verse
retains content. Rates use clean content characters, with a ±2-point band.
Mistranslation spans trim unchanged edges using the existing v3 normalizer.
The omission 20/40/40 event mix is a pooled, per-dose soft objective after dose
fit, nesting and retention of already passing selections; departures and
uncertain unit classifications remain visible. Seeded tie-breaking has a
five-second bound and falls back only to a verified feasible selection satisfying
the already fixed optimization priorities. This is not uniform random sampling.

Existing exact-context approvals are reused. An earlier 30% baseline is frozen
initially when the candidate bank can extend it to the complete numeric ladder.
A subsequent quality failure releases that freeze. The first repair selection
prefers already passing levels; the second may reconsider the lower doses. Otherwise,
a revised 30% draft may be selected and is explicitly marked; the original is
never overwritten. Older broad substitution spans can have a lower measured
rate after compact-span normalization even when their rendered text is identical.

Every new candidate is independently reviewed against the complete source
window. Each selected dose then receives combined-window review. The writer
sees failures for repair; the reviewer sees neither intended doses, QAs, answer
keys nor previous decisions. A passing 60% text alone is not a successful run:
all four nested levels must pass. Out-of-band or failed drafts remain held.
Verdicts are reused only for identical edits and the entire displayed context,
even if the dose label changes. A phrase quoted in a rejection is not treated
as inherently ungrammatical in another context.
The default bounds are five batches of up to twelve new candidates per window
and family, with two selection/review attempts per batch. Cached responses and
the full selection history are retained. These commands do not publish stimuli.

Mistranslation review now requires written gender agreement as a sixth check.
A clear `女儿…他` or female-only `女儿们…他们` mismatch is rejected, rather than
accepted as a contradiction flag. The writer must bundle dependent pronoun edits
with the gender-changing substitution at its first dose; their source characters
count toward coverage. Names alone do not establish gender, and pronouns referring
to different people are not globally replaced. Historical five-check approvals
cannot satisfy the new agreement gate without an exact-text audit.

For an existing local ladder, `evaluation.scripts.pipeline.repair_nested_agreement`
provides a bounded migration: audit all 32 mistranslation versions in the current
1 Kings 13 trial, request at most two model repairs per affected ladder, and rerun
all six checks on repaired wording. It patches only source pronouns, verifies
exact replay, dose and nesting, and retains the original texts and model responses.
Reviewed increments carry explicit prerequisites, so later increments cannot be
selected without the earlier context. Failed repairs stay held. This command
does not publish to the pilot or change the approved source candidate banks.

After explicit authorization to expand beyond the one-passage trial, the full
66-window campaign uses the same generation, review and bounded-repair rules:

```bash
python3 -u -m evaluation.scripts.pipeline.run_all_nested_window_defects \
  --output evaluation/runs/sol_nested_defects_all66_2026-11-19
python3 -m evaluation.scripts.pipeline.report_all_nested_status \
  evaluation/runs/sol_nested_defects_all66_2026-11-19/all_windows.json \
  deliverables/sol_nested_defects_all66_status.html
```

This produces 528 version slots (66 windows × two defect families × four doses).
Selection and the omission mix objective are fitted within each passage. Separate
family folders avoid concurrent writes to the same run state. The corrected
1 Kings 13 trial is reused only after source fingerprints, agreement policy,
required checks, exact replay and nesting are verified. Remaining jobs resume
from their caches. `jobs.json` distinguishes execution errors from completed
quality reviews; intermediate held statuses can still be repaired while a job
is running. Final results keep dose failures, reviewer failures and uncertainty
visible. No question bank, hosted passage or participant plan is published.

The full campaign defaults to resumable background API requests. Request IDs and
terminal responses are saved separately from validated results; interruption does
not require resubmitting accepted work. Both models and the review rubrics remain
unchanged. A malformed/incomplete structured response is retried at most once,
with the output allowance increased from 6,500 to 12,000 tokens (including
reasoning); invalid output is never treated as a candidate or approval. Effective
request budgets and transport are recorded. Previously valid cached results are
still reused. `ETEN_REVIEW_BACKGROUND=0` selects the original synchronous transport.

For larger fits, optimization of soft preferences (reviewed-selection retention,
mixture deviation and distance from dose centers) can retain a mechanically
verified feasible incumbent at the time limit. Dose-miss minimization precedes
that fallback; no dose, nesting, overlap or nonempty-verse constraint is relaxed.
`optimization_fallback_history` records when preference optimality was not proved.
If the joint fit times out before that stage, the same hard constraints are
solved separately for each window. This is recorded as
`joint_time_limit_per_window_fit`; the pooled mixture optimum is not claimed.
Cached linguistic approvals are reapplied separately from each level's numeric
dose gate, including final selection from review history. Passing wording at 50%
cannot cause an identical, out-of-band 60% cell to be labeled passed.

### Six defect levels on the Sol passages

Run `python3 -m evaluation.scripts.pipeline.build_clean_passage_ladder` from
the repository root to reproduce the 180 variants offline from the frozen
November 9 passages and their reviewed defect banks. The output directory is
`evaluation/datasets/passages/tier1_zh_sol_v1_defect_ladder_2026-11-09/`.
Its manifest lists the passages, coverage tolerance and exceptions.

Each passage JSON contains the clean and word-by-word controls plus six levels
per defect family. For example, `conditions.mistranslation10.text` is the
complete 10% passage. Its `actual_rate` is the measured fraction of source
content affected. Use `verses` for question windows. These labels come from
the clean passage when an omission removes a printed verse number. The
`selected_edits` in each condition point into the family's `edits` table,
which records exact character offsets and replacements on the clean text.

Omission and mistranslation use progressively larger sets of edits. Grammar
does the same except for Acts 20, which follows the historical rule allowing
different subsets of its five approved edits at 30%. Four omission texts
(15% and 30% in 2 Samuel 21 and Acts 20) were reselected to obtain six
strictly nested levels. The pilot versions are available in the source pack.

### Blinded Sol passages and reviewed MCQs

Run `python3 -m evaluation.scripts.pipeline.blind_reviewed122` to reproduce the
frozen bilingual release offline. The release uses the reviewed English and
Chinese forms in `datasets/pseudonym_remap/name_map_tier1_sol_reviewed122.json`.
The map records the parent map's checksum, both assigned names, the observed
passages, and the scoped rules used for ambiguous forms.

Under `evaluation/datasets/blinded/tier1_sol_reviewed122_v1/`, each passage file
contains the English source and the 20 Chinese conditions. Each of the 180
positive-dose conditions can be reconstructed from its blinded clean text and
rebased edit spans. The measured rates use the blinded character counts.
`qa/zh.json` and `qa/english.json` preserve item IDs, option order and keys
and draw their verse windows from the corresponding released passages.
`qa/pilot_review.json` carries the existing eligibility decisions.

`audit/choices.json` is for researchers. It contains the names matched in each
choice and the reviewed differences where the two source languages name someone
differently. Use question stems, choices, and passage text for participant
display. IDs, biblical references, eligibility, the map and the audit are
research metadata.

## Translate QA Pairs To Chinese

### Reviewed 122-question pilot bank

From the repository root, start Ollama on its default local port (11434) with
the `qwen3:8b` model installed. The verified writer uses Ollama 0.40.13,
checks the model's SHA-256 digest, and uses temperature 0 and seed 2026.
Run the translation and the two model checks:

```bash
python3 -m evaluation.scripts.pipeline.translate_reviewed122_zh
python3 -m evaluation.scripts.pipeline.verify_reviewed122_zh \
  --translations evaluation/runs/reviewed122_zh_focused_choices/zh.json \
  --run-dir evaluation/runs/reviewed122_zh_focused_choices/review --check-fidelity
python3 -m evaluation.scripts.pipeline.report_reviewed122_zh \
  --translations evaluation/runs/reviewed122_zh_focused_choices/zh.json \
  --run-dir evaluation/runs/reviewed122_zh_focused_choices/review
```

The writer uses `english.json` and `clean_zh_verses.json` under
`evaluation/datasets/qa/reviewed122/`. It translates the stem and each lettered
choice. Before translating, it uses the stem and all four English choices to identify
the fact each option supplies. It drops descriptions that do not answer the question
or distinguish the choices. It then checks the Chinese options against the original
English and uses any findings to revise the draft. The script copies the key and source
IDs from the English record.
The run directory contains the generated `zh.json`, per-question completions,
a manifest with the prompt, model digest, Ollama version, sampling settings
and input hashes, and `result.json` with the output hash.

Rerunning the first command resumes the same recipe. Use `--run-dir` with
a fresh directory for a new generation, or add `--item SOURCE_ID` for a
single-question replay. Exact text can vary with the inference runtime or hardware.
The review directory contains a passage-only answer check in `blind_audit.json`
and English-to-Chinese meaning checks for the stem and four choices in
`fidelity_audit.json`. The final command writes `translation_report.json`.
It combines those findings with checks for changes in what a question asks and
the previous pilot's passage-evidence holds. The generated bank is a candidate for pilot review.

### Other QA files

Run from the repository root:

```bash
export OPENAI_API_KEY=...
python evaluation/scripts/pipeline/translate_qa.py input.json evaluation/outputs/qa_zh.json
```

For open questions, the script translates the question but keeps the standard
answer in English. For MCQ questions, it translates the question and answer
options because the options are part of the question shown to the model.

Importer-native output:

```bash
python evaluation/scripts/pipeline/translate_qa.py input.json evaluation/outputs/qa_zh_native.json --format native
```

The old path still works as a compatibility wrapper:

```bash
python evaluation/scripts/archive/superseded/translate_llm_qa_to_chinese.py input.json evaluation/outputs/qa_zh.json
```

To inspect or translate QA after replacing canonical English terms with
protected source tokens:

```bash
python evaluation/scripts/data_prep/legacy/prepare_protected_qa.py \
  evaluation/datasets/qa/qa_output_luke_ch1_mixed.json \
  evaluation/outputs/qa_luke_ch1_protected.json
```

## Passage Translation Quality Baselines

`evaluation/scripts/scoring/current/translation_quality.py` defines passage translation methods for
quality experiments:

```bash
python evaluation/scripts/scoring/current/translation_quality.py \
  english_passage.txt \
  evaluation/outputs \
  --method google_word_by_word \
  --target-language zh-CN
```

When the output argument is a directory, the file is written to
`<output>/<method>/passage_translation.json`.

For English-to-Chinese Google word-by-word runs, the translator checks each recognized
name against the matching clean Sol verse and uses the reviewed Chinese spelling.
It recognizes complete Sol passages and consecutive full-verse excerpts. For other
passages, supply the aligned Chinese text with `--wbw-clean-passage clean_zh.txt`
to check the spelling in context. Without a reference, the output records a
glossary-only check. An unreviewed capitalized word or a conflicting name stops
generation and identifies the verse for review. The evaluation runner also
regenerates older cached passages that lack a matching name check.

Available methods:

```text
google_word_by_word
llm_prompt_low
llm_prompt_medium
llm_prompt_high
helsinki
mBART-50
nllb-200-distilled-600M
nllb-200-1.3B
```

The lowest baseline uses `deep_translator.GoogleTranslator` one whitespace token
at a time. The LLM methods use prompt-controlled quality. Helsinki, mBART-50,
and NLLB methods require `transformers`, `torch`, and `sentencepiece`. Their
model names can be overridden with `--helsinki-model`, `--mbart-model`,
`--nllb-distilled-model`, and `--nllb-model`.

## Generate Answers From Chinese Passage

Use the generated Chinese QA set as questions only. The agent strips answer,
correct-choice, and keyword fields before prompting the model.

```bash
export OPENAI_API_KEY=...
python evaluation/agents/generate_chinese_answers.py \
  evaluation/datasets/passages/luke_ch1_zh_passage.txt \
  evaluation/outputs/qa_zh.json \
  evaluation/outputs/generated_answers_zh.json
```

Local Ollama/Llama run:

```bash
ollama pull llama3.2:3b
ollama serve

python evaluation/agents/generate_chinese_answers.py \
  evaluation/datasets/passages/luke_ch1_zh_passage.txt \
  evaluation/outputs/qa_zh.json \
  evaluation/outputs/generated_answers_zh_llama.json \
  --provider ollama \
  --model llama3.2:3b
```

By default, answer generation sends only the referenced verse plus two verses
before and after it, based on each QA item's `passage_reference`. This keeps the
local 1B model prompt small and sends one question per model call. Use
`--verse-window -1` to send the full passage and use `--batch-size`.

On Apple Silicon, Ollama uses the local llama.cpp/Metal acceleration path when
available. Keep Ollama installed natively on macOS and run the command above;
the script talks to the local Ollama server.

Dry-run without calling the model:

```bash
python evaluation/agents/generate_chinese_answers.py \
  evaluation/datasets/passages/luke_ch1_zh_passage.txt \
  evaluation/outputs/qa_zh.json \
  evaluation/outputs/generated_answers_zh.redacted.json \
  --dry-run
```

## Score Generated Answers

Compare evaluator-generated answers against the standard QA answers. MCQ uses
direct choice comparison. Open generated answers are first back-translated from
Chinese into English, then scored against the English standard answers with
an LLM judge after back-translation.

```bash
export OPENAI_API_KEY=...
python evaluation/scripts/scoring/current/score_generated_answers.py \
  evaluation/outputs/generated_answers_zh_qwen.json \
  evaluation/outputs/qa_zh.json \
  evaluation/outputs/scores_zh_qwen.json
```

For a structure-only run without OpenAI calls:

```bash
python evaluation/scripts/scoring/current/score_generated_answers.py \
  evaluation/outputs/generated_answers_zh_qwen.json \
  evaluation/outputs/qa_zh.json \
  evaluation/outputs/scores_zh_qwen.no_ai.json \
  --skip-llm
```

## Controlled Mistranslation Variants

Create MQM `Accuracy > Mistranslation` variants by replacing content phrases
with same-role alternatives. The script copies the QA files and writes
`mistranslation_metadata.json` with both the requested and actual changed
content percentages.

For chapter-specific coverage, first generate and independently review banks.
Both stages now default to `gpt-6-sol`. Only candidates approved for a substantive
meaning change, fluency, pure substitution, locality, and validity in every
matched context enter the final bank. See [the script guide](scripts/README.md#gpt-6-sol-mistranslation-banks-and-independent-review)
for Tier 1 commands, review-only mode for existing banks, and cached/offline runs.
Entries are categorized as:

- `systematic`: when selected, all occurrences of that source phrase are
  replaced.
- `contextual`: selected occurrence-by-occurrence.

```bash
export OPENAI_API_KEY=...
python evaluation/scripts/variants/banks/generate_mistranslation_banks.py \
  --chapters 1 2 3 4 5 6 7 8 \
  --source-model-dir 1.7b \
  --source-method llm_prompt_high \
  --generator-model gpt-6-sol --judge-model gpt-6-sol \
  --output-name mistranslation_bank_sol_judged_zh.json
```

Then create deterministic variants. When `--bank` is omitted, the script uses
each chapter's bank named by `--chapter-bank-name`. Use `--require-judged-bank`
to require independent approvals and exact source/candidate bindings, and
`--require-bank` to prohibit the built-in fallback.

```bash
python evaluation/scripts/variants/current/create_mistranslation_variants.py \
  --chapters 1 2 3 4 5 6 7 8 \
  --source-model-dir 1.7b \
  --source-method llm_prompt_high \
  --chapter-bank-name mistranslation_bank_sol_judged_zh.json \
  --output-model-dir mistranslation_sol_judged \
  --require-bank --require-judged-bank \
  --rates 0% 5% 10% 15% 20% 30%
```

Use a custom substitution bank when you want tighter control over the exact
semantic swaps:

```bash
python evaluation/scripts/variants/current/create_mistranslation_variants.py \
  --chapters 2 \
  --bank evaluation/configs/mistranslation_bank_zh.json \
  --rates 5% 10% \
  --force
```

Bank format:

```json
{
  "schema_version": 1,
  "replacements": [
    {
      "source": "牧羊人",
      "target": "渔夫",
      "category": "entity",
      "mode": "systematic"
    },
    {
      "source": "三天",
      "target": "七天",
      "category": "number_time",
      "mode": "contextual"
    }
  ]
}
```

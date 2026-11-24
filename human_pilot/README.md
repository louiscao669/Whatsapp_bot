# Human pilot scripts

This directory contains the operational lifecycle for the human-participant
experiment. Run commands from the repository root.

```text
pilot_import.py                 import experiment content
build_experiment_plan.py        assign Latin-square condition plans
verify_experiment_delivery.py   verify variant passage resolution
verify_pilot_readiness.py       final study preflight
export_pilot_metrics.py         export timing and accuracy reports
export_pilot_responses.py       export evaluation-compatible responses
reset_experiment_plan.py        deliberate plan reset
pilot_wipe.py                   deliberate pilot-data removal
operations/                     participant and database administration
tests/                          offline regression tests
```

Normal preparation order:

```bash
python human_pilot/pilot_import.py
python human_pilot/build_experiment_plan.py --participant-ids id0,id1
python human_pilot/verify_pilot_readiness.py --participant-ids id0,id1
```

The reset, wipe, purge, migration, and translation-wipe tools can modify or
remove database state. Use their dry-run modes where available.

## Test the reviewed Chinese MCQs with the Sol passages

The [marked questions](../evaluation/reports/sol_option_provenance/marked_questions.md)
list the directly supplied Chinese fields in the local Sol release and reviewed drafts.
The Testing only panel displays the matching labels. The [bank records](../evaluation/datasets/qa/reviewed122_sol/manual_wording.json)
identify the exact stem, menu and key for each marked revision.
When submitting new editorial wording, set `manually_written_fields` on the pipeline input
entry or replacement approval, for example `["Q", "B"]` for a supplied stem and option B.
Review results carry the surviving labels, and the replacement selection includes them
alongside the candidate. When publishing a marked revision, use those fields in its bank record.

The `reviewed122_sol` test bank pairs eligible Chinese MCQs with ten Sol
passages using natural names. The release history and current eligibility are recorded in
`evaluation/datasets/qa/reviewed122_sol/pilot_review.json`.
The eight pilot slots use clean text twice and six defect conditions. The full
5–30% ladder and the pseudonymized passages are separate research materials.

The current English and Chinese source files are in
`evaluation/datasets/qa/reviewed122_sol/`. Wording revisions retain their
source IDs. The three new comprehension targets in the
[37-question publication](../evaluation/reports/sol_pilot_readiness_2026-11-12/publication.md)
have distinct source IDs linked to their original slots. The importer gives
revised questions their own database IDs so earlier responses still refer to
the wording shown.
The Chinese choice release in `choice_release.json` records revisions for all
117 eligible questions. The first release updated 105 questions. Of the 12
held for repair, 11 passed on the first repair and the Judges 9:18–20 question
passed on the second. The English file records the source questions.
All Sol MCQs offer **E. 无法判断** for readers who cannot answer
from the passage. The answer key uses A–D under every passage condition.

For new Chinese distractor batches, run
`python3 evaluation/scripts/mcq/preparation/rewrite_distractors.py sol --inputs INPUTS.json --output RUN_DIR`.
Use the same input format as the 117-item Sol batch (one `index` and Chinese `row`
per entry). The writer has up to three distractor drafts. A finding on the fixed
question or key sends the item back for a targeted wording repair. Previously
flagged wording that still appears in the item can be addressed in that same
proposal. The reviewer checks the full menu against the clean verses with the
key hidden, then checks the intended fact, answer evidence and reading burden.
If that review still flags the item, a second repair uses the latest wording
and addresses the outstanding findings. The reviewer checks the whole item
again. A pass ends the process immediately. An eligible published item that exhausts
its repair rounds receives an independent final review of its published stem, choices,
key and clean verse window. The reviewer can retire it for an unsupported target or
a giveaway that cannot be fixed with a fair four-choice menu testing the same fact.
Uncertain or repairable items stay held. Confirmed retirements update the local pilot
roster. The next pilot import withdraws those windows and preserves recorded answers.
Use `--preview-retirements` for a review-only run. For an earlier completed repair run,
use `--final-review-from RUN_DIR --output NEW_DIR` to assess exhausted items against
their published versions.

To return held items from an existing batch, use `--repair-held-from RESULTS.json`
in place of `--inputs` and choose a separate output directory. This explicit
return also includes items that exhausted all three distractor drafts. A held
item with one recorded repair starts directly at round two. Items that passed
or used both rounds are skipped. Resuming the same run reuses its saved
proposals and checks. The run writes each candidate and its repair history
to `results.json`. Publishing is separate.

Every Sol menu review now checks whether its correct answer needlessly repeats
the question, including paraphrased wording. A second check looks at relative
length. It flags a key for inspection if it has at least three more characters
than the longest distractor and is at least 35% longer than the middle-length
distractor. Counts include letters and digits and exclude punctuation, spaces,
and option E. The reviewer records why a longer answer needs its detail or
quotes the wording that can be shortened.

The distractor writer and menu reviewer also compare the clause structure of A–D.
If only the key has a second action, or only the key omits a result clause shared
by the three distractors, the pipeline requests a distractor repair. Two choices
using each construction are acceptable. The reviewer examines the actions and
their relationships, since a comma can also separate a list or an introductory phrase.

Run `python3 evaluation/scripts/mcq/preparation/rewrite_distractors.py sol --audit-published-keys --output RUN_DIR`
to screen the eligible published bank directly. This mode sends only flagged keys
to the writer. When all four choices start with the exact wording flagged as a
restatement of the question, removing it from the key also removes that opening
from the three distractors. The run records those edits and rechecks the full menu
and passage evidence. An unresolved review finding keeps the revision held.

The Sol menu review also checks the question and each of A–D for wording that
would make translation unnecessarily difficult. It looks for nested reports,
shifts in who does the action, unclear pronouns, formal idioms, and clauses
copied from the passage that state the same idea twice. It quotes each flagged
field so the repair can preserve the event, people and details being tested.
Use `--audit-translatability` in place of `--audit-published-keys` to run this
check on the published bank. Add `--item-id SOURCE_ID` to check a particular
question. The result is a source-wording review; individual target-language
translations can also be checked with readers.

Use `--audit-window-wording --inspect-only` to check every eligible Sol item for
unsupported assumptions, Chinese grammar and title consistency, and clues in the
options. The reviewer first sees only the stem and clean verses. It then checks
all four substantive choices. For parallel lists, the pipeline also checks whether
the most frequent entry in each position reconstructs the key. Omit `--inspect-only`
to send flagged items through the existing repair and verification rounds.

Run the stem review from the authoring checkout to update the published Sol bank.
It reads each Chinese question with its clean excerpt and the answer choices hidden.
It retires a question about the timing of a speech when the time evidence describes
a different event inside the speech. An uncertain finding is recorded for review.

```bash
python3 human_pilot/review_pilot_stems.py --output evaluation/runs/sol_stem_grounding --apply
```

Use `--item-id` to scope the same pipeline to one item. Omit `--apply` for a preview.
Publication records the evidence in the roster, withdraws the delivery window and
skips unanswered assignments. When a Sol item is retired, publication also finds
copies with the same source ID in the other live pilot banks. The reviewer checks
each copy against its own clean excerpt. Copies that fail are archived for future
assignment. Completed answers retain their original item and excerpt.
Use `--check-copies` without `--apply` to preview those decisions.

From the local repository, upload the runtime and released data using your VM's SSH alias.

```bash
sh deploy/deploy-vm.sh --host YOUR_VM_SSH_ALIAS --apply
```

On the VM, preview the bank against the configured database. For a first import
the preview reports the eligible question count and `existing=0`. Apply the import and
restart the platform. A repeat preview should report the same count for existing and eligible questions.

```bash
cd /opt/eten-whatsapp-bot
.venv/bin/python human_pilot/pilot_import_reviewed122.py --qa-set reviewed122_sol
.venv/bin/python human_pilot/pilot_import_reviewed122.py --qa-set reviewed122_sol --apply
sudo systemctl restart eten-platform
```

In **Admin → Participants → Create test participant**, select language **zh**
and choose **Sol Chinese · prepared QAs** for the questions adapted from
Prepared60, **Sol Chinese · generated from scratch** for the 66 released Hard77 questions,
or **Sol Chinese · natural names** for both. Keep **Build pilot
plan** and **Multiple-choice questions only** selected. Leave question types
and passage conditions unticked for the full selected set. Create the participant
and open its pilot link. Scoring uses the reviewed clean-passage answer key in
every condition, including when a mistranslation supports another option.

## Why the Chinese pilot excludes Grammar 15%

On 2026-11-13 we retained Grammar 30% and excluded Grammar 15% from the eight-slot
human pilot. In the original Sol passages, the two grammar doses yielded the same
aggregate multiple-choice accuracy across four small language model (SLM)
configurations on the 66 from-scratch questions. Each dose produced 190 correct
answers out of 264 (72.0%). Two-sided exact McNemar tests paired the same 66
questions within each configuration. None detected a statistically significant
difference between doses (all *p* ≥ 0.25). This evidence concerns model accuracy.
Human accuracy and reading time may respond differently. Omission and
mistranslation each retain both their 15% and 30% conditions.
[From-scratch SLM results](../evaluation/reports/sol_slides35_43_2026-11-13/from-scratch.html)

## Published research omission ladder (November 22)

The separate research release `sol-scratch65-omission-205030-ladder-v1` contains
551 approved window/dose variants at 5, 10, 15, 20, 25, 30, 40, 50 and 60 percent.
Its 34 held variants are excluded. Publication creates versioned
`ExperimentPassage` and verse records under `sol_omission205030_ladder_v1/`;
it creates no question, assignment, window or participant-plan records. These
higher experimental doses therefore do not enter the human Latin square.

```bash
python3 human_pilot/pilot_publish_omission_ladder.py --audit /tmp/research-omission-preview.json
python3 human_pilot/pilot_publish_omission_ladder.py --apply --preview /tmp/research-omission-preview.json --audit /tmp/research-omission-published.json
```

The package is hash-pinned. The publisher rejects changed existing content,
requires the matching preview, checks the live 15/30 participant release,
preserves pilot text and QA/group fingerprints, and verifies all research texts
again through a fresh database connection after committing. Repeating the
publication is idempotent. The frozen package is
`evaluation/datasets/passages/sol_scratch65_omission_205030_ladder_v1.json`.

## Launch the Chinese from-scratch study

### November 21 omission-only release

`sol_scratch65_omission_mix205030_v1.json` contains the reviewed 15% and 30%
omission versions for the 65 active from-scratch windows. The 20/50/30 word,
phrase and clause preference counts deletion occurrences pooled separately at
each dose. The doses are independently selected and retain the ±2 percentage
point limit. The held officer window remains excluded.

Use `human_pilot/pilot_publish_omission_mixture.py` for this content-only update.
It previews against the configured database, saves the complete before/after Sol
passage snapshot, and requires that exact preview when applying. It updates only
the from-scratch omission conditions, including restored verses, and checks all
eight rotations. Other conditions, prepared passages, QAs and group assignments
are preserved. Previously presented or answered assignment snapshots are kept.
Use fresh audit filenames for each publication attempt:

```bash
python human_pilot/pilot_publish_omission_mixture.py --audit /tmp/omission-preview.json
python human_pilot/pilot_publish_omission_mixture.py --apply --preview /tmp/omission-preview.json --audit /tmp/omission-applied.json
```

This publisher connects directly to the shared database; serving the new text
does not require a platform restart. The full-bank importer below manages the
earlier, broader window release and is a separate operation.

The Git release includes `sol_scratch66_windows_v1.json`. It fixes the Chinese verse text for each of the 66 windows under all seven conditions. Over a cohort of eight readers, each window appears twice clean and once in each of the other six conditions. The importer applies these window passages to the from-scratch bank only. Both Sol banks receive the current answer-choice wording.

Run the importer first without flags that write, then with `--apply`. To read back the persisted questions, keys, choices, groups and passages across all eight rotations, run:

```bash
.venv/bin/python human_pilot/pilot_import_reviewed122.py --qa-set reviewed122_sol --verify-installed
```

A successful check reports 66 windows, 330 dose variants, zero held, eight rotations and 528 presentations. This check creates no participant records. In-progress or previously shown assignments keep their displayed text. Unseen queued assignments receive the revised window.

The 15% and 30% doses use the countable Chinese characters in the clean window as denominator, with a tolerance of two percentage points. Omission counts deleted source characters. Grammar and mistranslation count the source spans replaced. The release retains the 320 passing variants from the matched draw. Ten previously held variants were repaired. Each records its earlier dose and repair provenance. Five of the ten use a documented phrase fallback, including both omission doses in Acts 23:25–26. Each repaired grammar passage passed a separate model review for a recognizable structural error and preserved meaning. Source spans intersecting the annotated answer evidence are recorded independently of the dose. Such an intersection alone does not establish that a reader can no longer recover the answer.

Use Chinese study accounts with target language `zh`. Each reader goes through consent
and the background questionnaire at their own `/pilot/<participant-id>` link.
The regular interface withholds the answer key, defect details and editorial labels.
Each reader sees the 66 questions once. The Latin square assigns one condition
to each material group, and the web pilot interleaves individual questions
from those groups throughout the session. Each trial records its actual position.

In the admin platform open **Participants → Study enrollment → Create study participant**.
Copy the personal pilot link for that reader. You can retrieve the link later from the
participant’s detail page. Each enrollment issues the next rotation in a group of eight.
Admin test runs have a separate rotation. An unused link or a screen-out still counts
as an issued rotation. A screen-out deletes the reader’s personal data.

For existing regular participant IDs, the CLI uses the same rotation counts.
From the project directory on the VM, substitute those participant IDs.
The first command previews the assignments. The second saves them.

```sh
.venv/bin/python human_pilot/build_experiment_plan.py --qa-set reviewed122_sol_scratch --participant-ids ID1,ID2 --dry-run
.venv/bin/python human_pilot/build_experiment_plan.py --qa-set reviewed122_sol_scratch --participant-ids ID1,ID2
```

The real-participant planner defaults to this set. It continues the rotation when more
readers enroll. The first eight cover every rotation. With twelve readers each material
group has three clean blocks. With sixteen each group has four clean blocks and two
under each other condition. These are assigned counts. Completed counts depend on
which readers finish.

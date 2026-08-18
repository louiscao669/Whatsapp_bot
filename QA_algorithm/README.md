# QA Algorithm

This folder contains scripts and outputs for question-selection and anchor-IRT
experiments.

## Structure

- `scripts/estimate_anchor_irt.py`
  - Estimates language model ability from gold anchor-passage responses using a
    transparent 1PL/Rasch MAP procedure.
- `scripts/build_anchor_irt_input.py`
  - Converts existing `scores_target_llama.json` outputs into the input format
    used by `estimate_anchor_irt.py`.
- `scripts/generate_passage_feature_profiles.py`
  - Generates passage-level feature profiles for QA scheduling using the
    question reference +/- 2 verses. **Deterministic** window: always centred
    on the reference, so window position is a constant function of the item.
- `scripts/anchor_irt/build_tier1_verse_windows.py`
  - The tier-1 counterpart, with a **randomized** 3-verse window: for each QA
    item it picks uniformly among the 3-verse windows that still contain
    everything the question needs, so the answer verse lands at a random
    position (first / middle / last) instead of always the centre.
  - Inputs: `inputs/tier1_required_spans.json` (per-question minimal
    answer-bearing span). Output: `inputs/tier1_qa_verse_windows.json` (verse
    numbers only, never verse text).
  - **Adding more QA items is safe.** Annotations are keyed by
    `{passage_id}:{sha1(normalized question)[:10]}`, not by position, so you can
    append, insert or reorder items in the tier-1 QA files and every existing
    item keeps the exact window it already had. Already-annotated questions are
    never re-judged; new ones are reported and left without a window until their
    required span is filled in (`--report-missing` writes a fill-in stub).
- `outputs/passage_feature_profiles/`
  - Generated passage-level feature profile JSON files.

## Commands

Generate passage feature profiles:

```bash
python3 QA_algorithm/scripts/generate_passage_feature_profiles.py \
  evaluation/datasets/passages/test_passage_luke1.txt \
  evaluation/datasets/qa/qa_output_luke_ch1_all_formats.json \
  QA_algorithm/outputs/passage_feature_profiles/luke1/passage_feature_profiles.json \
  --verse-window 2 \
  --model gpt-4.1-mini
```

Build the randomized tier-1 3-verse window map (93 items, 10 passages):

```bash
python3 QA_algorithm/scripts/anchor_irt/build_tier1_verse_windows.py --self-test

python3 QA_algorithm/scripts/anchor_irt/build_tier1_verse_windows.py \
  --qa-root "/path/to/ETEN-Bible-translation-project/v3/combo/qa_generation" \
  --spans   QA_algorithm/inputs/tier1_required_spans.json \
  --out     QA_algorithm/inputs/tier1_qa_verse_windows.json \
  --seed    20260803
```

After adding QA items, see which ones still need a required span and get a
fill-in stub for exactly those (existing items are untouched):

```bash
python3 QA_algorithm/scripts/anchor_irt/build_tier1_verse_windows.py \
  --qa-root ... \
  --spans   QA_algorithm/inputs/tier1_required_spans.json \
  --out     QA_algorithm/inputs/tier1_qa_verse_windows.json \
  --report-missing QA_algorithm/inputs/tier1_spans_TODO.json
```

Review each entry in the stub (does the gold answer actually live in that verse?
is the verse syntactically headless?), then merge it into
`tier1_required_spans.json` and re-run. Or let the LLM judge only the new ones:

```bash
python3 ... --llm-spans --only-new --spans-out QA_algorithm/inputs/tier1_required_spans.json
```

Re-derive ALL required spans with an LLM (gpt-4.1-mini, temperature 0) and
report where it disagrees with the checked-in annotation:

```bash
python3 QA_algorithm/scripts/anchor_irt/build_tier1_verse_windows.py \
  --qa-root ... --spans QA_algorithm/inputs/tier1_required_spans.json \
  --out /tmp/windows_llm.json --llm-spans --spans-out /tmp/llm_spans.json \
  --compare-spans
```

Run anchor IRT self-test:

```bash
python3 QA_algorithm/scripts/estimate_anchor_irt.py --self-test
```

Run anchor IRT on an input JSON:

```bash
python3 QA_algorithm/scripts/estimate_anchor_irt.py \
  --input-json path/to/anchor_irt_input.json \
  --output-json QA_algorithm/outputs/anchor_irt_estimates.json
```

Build open-question anchor IRT input from current Luke 1-8 model score files:

```bash
python3 QA_algorithm/scripts/build_anchor_irt_input.py \
  --q-type open \
  --output-json QA_algorithm/inputs/anchor_irt_input_open.json
```

Estimate model ability from that converted input:

```bash
python3 QA_algorithm/scripts/estimate_anchor_irt.py \
  --input-json QA_algorithm/inputs/anchor_irt_input_open.json \
  --output-json QA_algorithm/outputs/anchor_irt_estimates_open.json
```

For MCQ-only or combined inputs, change `--q-type`:

```bash
python3 QA_algorithm/scripts/build_anchor_irt_input.py --q-type mcq
python3 QA_algorithm/scripts/build_anchor_irt_input.py --q-type all
```

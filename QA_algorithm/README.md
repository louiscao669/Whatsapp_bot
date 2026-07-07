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
    question reference +/- 2 verses.
- `outputs/passage_feature_profiles/`
  - Generated passage-level feature profile JSON files.

## Commands

Generate passage feature profiles:

```bash
python3 QA_algorithm/scripts/generate_passage_feature_profiles.py \
  evaluation/datasets/test_passage_luke1.txt \
  evaluation/datasets/qa_output_luke_ch1_all_formats.json \
  QA_algorithm/outputs/passage_feature_profiles/luke1/passage_feature_profiles.json \
  --verse-window 2 \
  --model gpt-4.1-mini
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

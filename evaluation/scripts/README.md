# Evaluation scripts

- `data_prep/`: passage and QA preparation, translation, and canonicalization.
- `variants/`: perturbation-bank generation and passage-variant creation.
- `pseudonyms/`: pseudonym-map construction and application.
- `mcq/`: MCQ rewriting, diagnostics, regeneration, and repair.
- `scoring/`: answer generation and translation-quality scoring.
- `analysis/`: sensitivity, separability, and model-comparison analyses.
- `reporting/`: report and visualization generation.
- `campaigns/`: multi-step shell runners.
- `_common.py`: shared utilities used across script groups.

Run commands from the repository root unless a script explicitly says otherwise.

## Import missing Gold-72 QA artifacts

Build open and MCQ forms for the selected questions absent from the canonical
Tier-1 QA set, merge them idempotently into the master and per-passage files,
and regenerate the affected BSB-pseudonymized QA files:

```bash
python3 evaluation/scripts/data_prep/import_tier1_gold_qa.py
```

Validate the same operation without writing first:

```bash
python3 evaluation/scripts/data_prep/import_tier1_gold_qa.py --dry-run
```

The command finishes only when the canonical and BSB-pseudonymized directories
both provide open and MCQ artifacts for all 72 selected content IDs.

Fetch an English BibleGateway passage for the MCQ dataset:

```bash
python evaluation/scripts/data_prep/fetch_biblegateway_passage.py "Micah 5:4-20"
```

This writes `evaluation/datasets/mcq/passages/mich_5_4-20.txt` by default. Use
`--version` to select another English BibleGateway translation and `--force`
to replace an existing file.

Fetch every passage in the tier-1 CSV's `reference` column:

```bash
python evaluation/scripts/data_prep/fetch_biblegateway_passage.py \
  --csv evaluation/datasets/obscure_narrative_passages_tier1.csv
```

Existing files are skipped, so the command is safe to resume. It also supports
cross-chapter references such as `Judges 17:1-18:31`.

# Evaluation

Evaluation utilities, generated datasets, and local outputs for answer generation
and scoring experiments.

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

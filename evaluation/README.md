# Evaluation

Evaluation utilities, generated datasets, and local outputs for answer generation
and scoring experiments.

## Full Pipeline

Run from the repository root with a canonical Chinese passage and the original
English QA set:

```bash
export OPENAI_API_KEY=...
python evaluation/main.py \
  evaluation/datasets/luke_ch1_zh_passage.txt \
  path/to/qa_original_english.json \
  --run-name luke_ch1
```

python evaluation/main.py \
  evaluation/datasets/luke_ch1_zh_passage.txt \
  "/Users/louiscao/bible translation/ETEN-Bible-translation-project/v3/combo/qa_generation/outputs/full_pipeline/qa_output_luke_ch1_mixed.json" \
  --run-name luke_ch1 \
  --skip-llm-quality-methods


python evaluation/main.py evaluation/datasets/test_passage_luke1.txt "/Users/louiscao/bible translation/ETEN-Bible-translation-project/v3/combo/qa_generation/outputs/full_pipeline/qa_output_luke_ch1_mixed.json" \
    --skip-llm-quality-methods \
    

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
  evaluation/datasets/test_passage_luke1.txt \
  evaluation/datasets/qa_output_luke_ch1_mixed.json \
  --answer-provider ollama \
  --answer-model llama3.2:3b \
  --force-answer
```

## Translate QA Pairs To Chinese

Run from the repository root:

```bash
export OPENAI_API_KEY=...
python evaluation/scripts/translate_llm_qa_to_chinese.py input.json evaluation/outputs/qa_zh.json
```

For open questions, the script translates the question but keeps the standard
answer in English. For MCQ questions, it translates the question and answer
options because the options are part of the question shown to the model.

Importer-native output:

```bash
python evaluation/scripts/translate_llm_qa_to_chinese.py input.json evaluation/outputs/qa_zh_native.json --format native
```

The old path still works as a compatibility wrapper:

```bash
python scripts/translate_llm_qa_to_chinese.py input.json evaluation/outputs/qa_zh.json
```

To inspect or translate QA after replacing canonical English terms with
protected source tokens:

```bash
python evaluation/scripts/prepare_protected_qa.py \
  evaluation/datasets/qa_output_luke_ch1_mixed.json \
  evaluation/outputs/qa_luke_ch1_protected.json
```

## Passage Translation Quality Baselines

`evaluation/scripts/translation_quality.py` defines passage translation methods for
quality experiments:

```bash
python evaluation/scripts/translation_quality.py \
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
  evaluation/datasets/luke_ch1_zh_passage.txt \
  evaluation/outputs/qa_zh.json \
  evaluation/outputs/generated_answers_zh.json
```

Local Ollama/Llama run:

```bash
ollama pull llama3.2:3b
ollama serve

python evaluation/agents/generate_chinese_answers.py \
  evaluation/datasets/luke_ch1_zh_passage.txt \
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
  evaluation/datasets/luke_ch1_zh_passage.txt \
  evaluation/outputs/qa_zh.json \
  evaluation/outputs/generated_answers_zh.redacted.json \
  --dry-run
```

## Score Generated Answers

Compare evaluator-generated answers against the standard QA answers. MCQ uses
direct choice comparison. Open generated answers are first back-translated from
Chinese into English, then scored against the English standard answers with
embedding cosine similarity and an LLM judge.

```bash
export OPENAI_API_KEY=...
python evaluation/scripts/score_generated_answers.py \
  evaluation/outputs/generated_answers_zh_qwen.json \
  evaluation/outputs/qa_zh.json \
  evaluation/outputs/scores_zh_qwen.json
```

For a structure-only run without OpenAI calls:

```bash
python evaluation/scripts/score_generated_answers.py \
  evaluation/outputs/generated_answers_zh_qwen.json \
  evaluation/outputs/qa_zh.json \
  evaluation/outputs/scores_zh_qwen.no_ai.json \
  --skip-llm \
  --skip-embeddings
```

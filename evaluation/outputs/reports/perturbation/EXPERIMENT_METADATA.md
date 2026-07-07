# Evaluation Output Metadata

This folder contains translated passage outputs, answer-model outputs, scoring
outputs, and synthetic perturbation experiments for the Luke evaluation pipeline.

The main research question is whether answer accuracy reflects translation
quality. The synthetic folders intentionally degrade a strong baseline
translation, usually `1.7b/llm_prompt_high`, in controlled ways. The QA set is
kept fixed and high quality; the perturbation is applied to the translated
passage, then the answer model answers from that perturbed passage.

## Standard Model Output Folders

Folders such as `1.5b`, `1.7b`, and `llama 1b` contain normal translation,
answering, backtranslation, and scoring runs.

Typical method folders inside them are:

- `llm_prompt_high`: LLM passage translation with the strongest prompt.
- `llm_prompt_medium`: LLM passage translation with the medium prompt.
- `llm_prompt_low`: LLM passage translation with the weaker prompt.
- `nllb-200-1.3B`: NLLB 1.3B passage translation.
- `nllb-200-distilled-600M`: distilled NLLB passage translation.
- `mBART-50`: mBART passage translation.
- `helsinki`: Helsinki/OPUS machine translation.
- `google_word_by_word`: Google word-by-word style baseline.
- `_shared`: shared assets such as translated QA, entity inventory, and
  decanonicalized QA files.

The QA translation is intended to be shared across methods so the experiment
tests passage translation quality, not different QA translations.

## Synthetic Perturbation Folders

The synthetic folders are usually placed under each chapter folder, for example:

```text
evaluation/outputs/luke1/omission/5%
evaluation/outputs/luke1/addition/bad_10%
evaluation/outputs/luke1/inconsistency/name_15%
```

Each perturbation folder should contain the external artifacts needed by
`evaluation/main.py`:

- `passage_translation.json`
- `passage_target.txt`
- `passage_target_decanonicalized.txt`
- `qa_target_decanonicalized.json`

After answering/scoring, it may also contain:

- `generated_answers_target_llama.json`
- `generated_answers_target_llama_backtranslated.json`
- `scores_target_llama.json`

Most synthetic scripts also write a metadata file, such as
`omission_metadata.json`, `addition_metadata.json`, or
`grammar_metadata.json`, with the exact selected clauses/replacements and the
actual achieved rate.

## Rate Meaning

Folders named `5%`, `10%`, `15%`, etc. generally mean the target percentage of
passage content characters to affect. They are not exact percentages of verses
or questions.

Because perturbations operate on clauses or replacement spans, the achieved
rate can be slightly higher or lower than the requested rate. Use each folder's
metadata JSON for the exact actual rate.

## `omission`

Purpose: simulate MQM Accuracy > Omission.

What it does:

- Splits the translated passage into verse-aware clause units.
- Randomly removes clauses until the target content-character rate is reached.
- Keeps the QA set unchanged.

Interpretation:

- If answer accuracy drops, the omitted content likely removed information
  needed to answer questions.
- If open-answer LLM score remains high, many omitted clauses may not be
  question-relevant, or the answer model may infer from nearby context.

Primary script:

```text
evaluation/scripts/create_omission_variants.py
```

Metadata:

```text
omission_metadata.json
```

## `addition`

Purpose: simulate MQM Accuracy > Addition and test robustness to extra content.

What it does:

- Copies a clean baseline passage.
- Inserts extra clauses until the target content-character rate is reached.
- Supports three categories:
  - `neutral`: plausible but mostly irrelevant extra information.
  - `bad`: noisy or incorrect additions that are not directly MCQ distractors.
  - `adversarial`: misleading additions derived from wrong MCQ options and
    inserted near the referenced verse when possible.

Interpretation:

- `neutral_*` tests whether harmless noise affects QA.
- `bad_*` tests whether wrong but generic added information affects QA.
- `adversarial_*` intentionally pressures MCQ accuracy and should be
  interpreted as a stress test, not a natural translation error distribution.

Primary script:

```text
evaluation/scripts/create_addition_variants.py
```

Bank:

```text
evaluation/datasets/addition_bank.json
```

Metadata:

```text
addition_metadata.json
```

## `grammar`

Purpose: simulate MQM Fluency > Grammar while trying to preserve core meaning.

What it does:

- Selects clause units up to the target affected-character rate.
- Applies rule-based Chinese grammar degradations.
- Avoids punctuation-only edits.
- Protects placeholders and verse numbers.

Current grammar operations include:

- Function-word deletion.
- Aspect marker misuse.
- Classifier / measure-word awkwardness.
- Local phrase order disorder.
- Agreement / connective awkwardness.

Interpretation:

- This tests whether QA accuracy is sensitive to fluency problems when meaning
  is mostly recoverable.
- A small QA drop with a large MQM fluency penalty would suggest answer
  accuracy under-detects fluency degradation.

Primary script:

```text
evaluation/scripts/create_grammar_variants.py
```

Metadata:

```text
grammar_metadata.json
```

## `inconsistency`

Purpose: simulate MQM Fluency/Terminology > Inconsistency.

What it does:

- Creates two separate inconsistency types:
  - `name_*`: inconsistent names/entities, such as one entity being rendered
    with multiple Chinese forms.
  - `style_*`: inconsistent register/style, such as formal biblical wording
    mixed with casual modern wording.
- Applies replacements until the target affected-character rate is reached.

Interpretation:

- `name_*` is more likely to affect entity tracking and QA accuracy.
- `style_*` may lower MQM quality without strongly lowering QA accuracy.

Primary script:

```text
evaluation/scripts/create_inconsistency_variants.py
```

Metadata:

```text
inconsistency_metadata.json
```

## `awkward`

Purpose: simulate MQM Style > Awkward / source-interference problems.

What it does:

- Copies a clean baseline translation.
- Replaces natural Chinese expressions with literal, over-explicit, or
  source-like Chinese expressions.
- Uses chapter-specific LLM-generated replacement banks when available.
- Falls back to the global awkward-style bank otherwise.

Examples of intended error shape:

- Natural verb becomes inflated light-verb phrasing.
- Natural biblical expression becomes over-explicit literal phrasing.
- Compact Chinese phrase becomes source-like linearized wording.

Interpretation:

- This should mainly affect naturalness and style, while preserving most
  answer-relevant meaning.
- If QA accuracy stays high, that supports the claim that answer accuracy does
  not fully capture style/fluency quality.

Primary scripts:

```text
evaluation/scripts/generate_chapter_awkward_style_banks.py
evaluation/scripts/create_awkward_style_variants.py
```

Banks:

```text
evaluation/datasets/awkward_style_bank.json
evaluation/datasets/chapter_awkward_style_banks/
```

Metadata:

```text
awkward_style_metadata.json
```

## `mistranslation`

Purpose: simulate MQM Accuracy > Mistranslation.

What it does:

- Replaces one content phrase with a different content phrase of a similar
  broad role.
- Intended to change meaning without deleting text or adding new clauses.
- Examples include entity, role, location, number, or time substitutions.

Interpretation:

- This is a direct semantic accuracy degradation.
- QA accuracy should drop most when the substituted content is relevant to the
  questions.

Primary scripts:

```text
evaluation/scripts/generate_mistranslation_banks.py
evaluation/scripts/create_mistranslation_variants.py
```

Metadata:

```text
mistranslation_metadata.json
```

## `untranslated`

Purpose: simulate MQM Locale Convention / Untranslated Text, but this
experiment has an important caveat.

What it does:

- Replaces selected translated Chinese clauses with the corresponding English
  source clauses from the same verse.

Interpretation caveat:

- If the answer model understands English, this may not degrade QA accuracy.
- In that case the experiment tests mixed-language robustness, not Chinese
  translation usability.
- Treat this as secondary unless the answer model is restricted to Chinese.

Primary script:

```text
evaluation/scripts/create_untranslated_variants.py
```

Metadata:

```text
untranslated_metadata.json
```

## `nllb_dropout`

Purpose: create a stochastic NLLB translation-quality gradient.

What it does:

- Translates with `facebook/nllb-200-1.3B`.
- Runs greedy decoding with `num_beams=1`.
- Applies dropout during inference by setting dropout modules/fields to the
  requested rate while keeping the top-level model in eval mode.

Interpretation caveat:

- Dropout may not create a smooth or obvious quality gradient for every
  passage.
- Very similar outputs across rates should be treated as weak degradation, not
  as evidence that the intended rate produced meaningful translation damage.

Primary implementation:

```text
evaluation/scripts/translation_quality.py
```

Method names:

```text
nllb-200-1.3B-dropout-0.0
nllb-200-1.3B-dropout-0.05
nllb-200-1.3B-dropout-0.1
...
```

## Recommended Interpretation

Use QA accuracy as one outcome, not the whole translation-quality measure.

Expected high-level pattern:

- Omission and mistranslation should be most likely to reduce QA accuracy when
  they touch answer-relevant content.
- Addition, especially adversarial addition, can reduce MCQ accuracy but may be
  less natural as a translation-error simulation.
- Grammar, awkward style, and style inconsistency may receive worse MQM scores
  while preserving QA accuracy.
- Untranslated text is confounded when the answer model is multilingual.

The strongest analysis is to compare QA accuracy against MQM category scores by
chapter, method, perturbation type, and perturbation rate.

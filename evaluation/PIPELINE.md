# English passage → pseudonymized Chinese: end-to-end workflow

How a plain English test passage becomes the blinded, pseudonymized Chinese
materials that the answer models (and eventually WhatsApp participants) see.

Stages 1–5 and 9 are `evaluation/main.py`. Steps 0, 6, 7, and 8 are separate
scripts run around it. Run everything from the repository root unless a command
says otherwise.

**Why blinding at all:** the answer model stands in for a native speaker reading
the translation. If canonical names survive, the model answers from its Bible
priors instead of from the translated text, and QA accuracy stops measuring
translation quality. Every step below exists to keep the passage recoverable
*only* from itself.

---

## Stage map

| # | Stage | Entry point | Key output |
|---|---|---|---|
| 0 | Fetch English passage | `data_prep/fetch_biblegateway_passage.py` | `datasets/passages/test_passage_lukeN.txt` |
| 1 | Entity inventory | `main.py` (`entity-inventory`) | `_shared/<run>_entity_inventory.json` |
| 2 | Translate QA to Chinese | `main.py` (`translate`) | `_shared/<run>_qa_zh.json` |
| 3 | Protect source + translate passage | `main.py` (`passage-translate`) | `<method>/passage_target.txt` |
| 4 | Decanonicalize | `main.py` (`decanonicalize`) | `<method>/passage_target_decanonicalized.txt` |
| 5 | Defect variants | `scripts/variants/create_*_variants.py` | `<method>/<defect>/<rate>%/` |
| 6 | **Tag section headers** | `data_prep/tag_passage_headers.py` (+ manual LLM) | `<header>…</header>` in place |
| 7 | Build pseudonym remap | `pseudonyms/build_pseudonym_remap.py` | `datasets/pseudonym_remap/lukeN_remap.json` |
| 8 | Apply pseudonyms | `pseudonyms/apply_pseudonym_remap.py` | `passage_target_pseudonymized.txt` |
| 9 | Answer → back-translate → score | `main.py` | `scores_target_llama.json` |

---

## 0. Fetch the English passage

```bash
python evaluation/scripts/data_prep/fetch_biblegateway_passage.py "Micah 5:4-20"
```

BibleGateway has no public API, so this parses the browser page and fails loudly
rather than writing an empty file if the markup changes. Output is NIV text with
verse numbers, footnote markers (`[a]`), and bare section headings.

## 1. Entity inventory

`run_entity_inventory_stage` asks an LLM to enumerate the chapter's entities and
assigns each a typed placeholder pair from `ENTITY_TYPE_CONFIG`:

| Type | Protected token | Chinese placeholder |
|---|---|---|
| person | `PERSON` | 人物 |
| place | `PLACE` | 地点 |
| group | `GROUP` | 群体 |
| role | `ROLE` | 角色 |
| object | `OBJECT` | 物件 |
| title | `TITLE` | 称号 |
| other | `ENTITY` | 实体 |

Written to `_shared/<run-name>_entity_inventory.json`. Disable with
`--skip-entity-discovery`, which falls back to the hardcoded `DEFAULT_MAPPING` /
`DEFAULT_ENGLISH_TOKEN_MAPPING` tables in `decanonicalize_chinese_dataset.py`
(Luke-specific).

## 2. Translate the QA set to Chinese

Shared across all methods, so translation noise in the questions is held
constant while passage quality varies. Questions and MCQ options are translated;
**open standard answers stay in English** — they are the scoring rubric, not
participant-facing. MCQ options are translated because they are part of the
displayed question.

## 3. Protect the source, then translate the passage

Per method. `run_passage_translate_stage` branches on `uses_natural_source_text()`:

- **Protected-token path** — `llm_prompt_low/medium/high`, `google_word_by_word`.
  English canonical names are replaced with `__PERSON_C__`-style tokens before
  translation, using `DEFAULT_ENGLISH_TOKEN_MAPPING` plus the entity inventory
  (and `--mapping-json` if given).
- **Natural-source path** — `helsinki`, `mBART-50`, `nllb-200-distilled-600M`,
  `nllb-200-1.3B`, and every `nllb-200-1.3B-dropout-*` rate. These receive the
  **unmodified English**, because the neural MT models mangle the protected
  tokens.

Writes `passage_source_decanonicalized.txt` (what was actually sent) and
`passage_target.txt` (the Chinese) into `<output-dir>/<method>/`.

## 4. Decanonicalize

`run_decanonicalize_stage` runs for every method, but the work differs sharply by
branch:

- Protected-token methods arrive already carrying `__PERSON_C__`, so
  canonicalization is close to a lookup: token → placeholder (人物丙).
- Natural-source methods arrive carrying **real Chinese Bible names** (耶稣,
  加利利, 撒迦利亚) or machine transliterations of them, so the LLM has to do
  genuine entity recognition on possibly-garbled Chinese.

`llm_canonicalize_passage()` gets a mapping table from `canonicalization_entries()`
with four fields per entity — `placeholder`, `protected_token`, `english_aliases`,
`chinese_alias_hints` — and is instructed that aliases "may be translated,
transliterated, abbreviated, or awkwardly machine-translated." It must emit the
placeholder, never the protected token, and must preserve verse numbers and
compound verb-object grammar (烧香 → 烧材料甲, not deletion).

Note that `DEFAULT_MAPPING` enters here as `chinese_alias_hints` — hints to the
LLM, not a deterministic find-and-replace. The standalone
`decanonicalize_chinese_dataset.py` does apply it deterministically via
`replace_text`, but `main.py` does not use that path for the passage.
`cleanup_protected_tokens()` then sweeps any leaked `__TOKEN__` via
`PROTECTED_TOKEN_MAPPING`.

Outputs `passage_target_decanonicalized.txt`, `qa_target_decanonicalized.json`,
and `decanonicalized_metadata.json` — whose `canonicalization.mapping` is the
input to stage 7.

## 5. Defect variants

```bash
python evaluation/scripts/variants/create_omission_variants.py \
  --chapters 1 2 3 4 5 6 7 8 --rates 0% 5% 10% 15% 20% 30%
```

Fans the decanonicalized passage into condition directories. The committed pilot
set is 7 conditions: `omission/0%|10%|20%|30%`, `mistranslation/20%`,
`grammar/30%`, `google_word_by_word`. Mistranslation banks are LLM-proposed then
validated and frozen, with entries marked `systematic` (all occurrences) or
`contextual` (occurrence-by-occurrence).

## 6. Tag section headers ← the manual LLM step

```bash
python evaluation/scripts/data_prep/tag_passage_headers.py --dry-run
python evaluation/scripts/data_prep/tag_passage_headers.py
```

Wraps heading lines as `<header>…</header>` in `passage_target.txt`,
`passage_target_decanonicalized.txt`, and `passage_target_backcanonicalized.txt`
under `outputs/luke{ch}/{model}/`. Idempotent; preserves line endings.

A line is treated as a heading if it is blank-line-preceded, carries no verse
marker, and the *next* line begins a verse listed in `SECTION_STARTS` — a
**hardcoded table covering Luke 1–8 only**. The next-line check is what stops
unnumbered poetry continuation lines from being mistaken for headings.

**This is why the step is manual for anything else.** For a new passage you ask
an LLM to identify the section headings in the text and wrap them, or to give you
the section-start verse numbers so `SECTION_STARTS` can be extended.

Two reasons it matters downstream:

1. `index_passage_verses()` in `agents/generate_chinese_answers.py` slices the
   passage on verse-number markers. An untagged heading has no verse number, so
   it is absorbed into the **preceding** verse's chunk and drifts into the wrong
   ±2-verse answer window.
2. Headings are answer spoilers. "Jesus Heals a Man With Leprosy" gives away the
   question. `scripts/mcq/regen_mcq_tier01.py` strips them with its `HEADER`
   regex — which only works if they are tagged.

Run this **before** stage 8 so the tags propagate into the pseudonymized files.

## 7. Build the pseudonym remap

```bash
cd evaluation && python scripts/pseudonyms/build_pseudonym_remap.py
```

Reads `canonicalization.mapping` from each chapter's
`decanonicalized_metadata.json` and turns bare placeholders into readable
pseudonyms while staying blind. Keyed on English aliases, so an entity keeps the
same pseudonym in every chapter. Pinned names are honoured exactly and removed
from the pools to prevent collisions.

| Class | Policy | Example |
|---|---|---|
| person | gendered transliteration | 耶稣 → 玛伦, 马利亚 → 芮茉 |
| group | collective name | 以色列 → 泰隆 |
| place | transliteration + type suffix (地/城/村) | 加利利 → 迦洛地 |
| deity | distinct neutral title | 神 → 至高者, 主 → 主 |
| generic | plain Chinese word restored (not a spoiler) | 船, 门徒, 祭司, 香 |
| text | "this account" | — |

Writes `datasets/pseudonym_remap/lukeN_remap.json` and prints a doubling scan.

## 8. Apply the remap

```bash
cd evaluation
python scripts/pseudonyms/apply_pseudonym_remap.py --dry-run
python scripts/pseudonyms/apply_pseudonym_remap.py
```

Rewrites **Chinese content only** — both placeholders and any leaked canonical
name, longest token first — then `collapse_repeats()` fixes artifacts like
至高者 至高者 → 至高者. English fields (open answers, keywords) are untouched
because they are the rubric.

Produces `passage_target_pseudonymized.txt` per chapter × condition (56 files at
the 7 pilot conditions) and `qa_target_pseudonymized.json` per chapter, then runs
a doubling/leak scan across every output with
`LEAK_IGNORE = {神, 主, 香, 灵}` excluded as legitimately ambiguous.

## 9. Answer, back-translate, score

Answer generation sends the referenced verse plus `--answer-verse-window 2`
verses either side, one question per call, to keep the local 1B model's prompt
small. Open answers are back-translated to English, then judged against the
original English standard answers. MCQ uses direct choice comparison.

---

## Open issue: blinding is not symmetric across methods

The two branches in stage 3 do not give equally strong guarantees.

- **LLM-prompt methods and `google_word_by_word`** — names are destroyed *before*
  translation. The canonical identity is not recoverable from the Chinese, no
  matter what the MT model or the canonicalizer does. Blinding is guaranteed by
  construction.
- **`helsinki`, `mBART-50`, both NLLB models, and the entire dropout gradient** —
  names survive translation intact, and blinding depends entirely on one
  post-hoc LLM pass catching every mention, including mangled transliterations.
  Blinding is best-effort.

The accumulated evidence of that difficulty is visible in `DEFAULT_MAPPING`
itself: entries like `"圣鬼": "灵甲"` (an MT model rendering *Holy Spirit* as
"holy ghost/demon") and `"最高者": "尊者甲"` are hand-added catches for exactly
this failure mode.

Each miss puts a canonical name in front of the answer model, which lets it fall
back on Bible priors and inflates accuracy for that cell — and only for
natural-source cells.

**Possible bearing on two known findings.** This is a hypothesis, not a
measurement:

- The method-quality ordering is noisy, and the noise would be concentrated in
  the natural-source methods, which are exactly the ones without guaranteed
  blinding.
- The dropout gradient is flat (luke1: 0.864 / 0.841 / 0.864 / 0.841 at dropout
  0.0–0.2). Higher dropout garbles output → weirder transliterations → higher
  canonicalizer miss rate → more leaked priors, pushing accuracy *up* precisely
  where the defect should push it *down*. A leak rate that rises with dropout
  would partially cancel the dose-response.

**Proposed check.** Count canonical-name survivals in
`passage_target_decanonicalized.txt`, broken down by method and by dropout rate.
If the leak rate is flat across dropout, this explanation is ruled out and the
flat gradient is a real property of dropout as a quality knob. If it rises, the
dropout results need re-running with a stronger blinding guarantee for the
natural-source path.

A stronger guarantee is available cheaply: run the natural-source methods on the
protected-token English as well, and use the divergence between the two runs to
quantify how much the canonicalizer is missing.

---

## File layout reference

```
evaluation/
  datasets/
    passages/        test_passage_lukeN.txt        English source
    qa/              qa_output_luke_chN_*.json     English QA (imported from qa_generation)
    perturbations/   defect banks
    pseudonym_remap/ lukeN_remap.json              stage 7 output
  outputs/                                          → symlink to eten-research-outputs/
    _shared/         <run>_entity_inventory.json, <run>_qa_zh*.json
    luke{N}/{model}/{method}/
      passage_source_decanonicalized.txt            what was sent to the MT model
      passage_translation.json
      passage_target.txt                            raw Chinese
      passage_target_decanonicalized.txt            placeholders
      passage_target_pseudonymized.txt              participant-facing
      qa_target_decanonicalized.json
      qa_target_pseudonymized.json
      decanonicalized_metadata.json                 canonicalization.mapping
      generated_answers_target_llama.json
      generated_answers_target_llama_backtranslated.json
      scores_target_llama.json
```

Every `main.py` stage reuses its existing output file unless it is missing or you
pass `--force` / `--force-translate` / `--force-passage-translate` /
`--force-decanonicalize` / `--force-answer` / `--force-backtranslate` /
`--force-score`. Cached reuse can hide upstream changes — force the stage when in
doubt.

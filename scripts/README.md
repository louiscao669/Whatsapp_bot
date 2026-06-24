# Test scripts

## Translate LLM QA output to Chinese

Translate a mixed open-QA/MCQ JSON file shaped like:

```json
[
  {"q_type": "open", "Q": "Who was with Luke?", "A": "The eyewitnesses."},
  {
    "q_type": "mcq",
    "Q": "Who was with Luke?",
    "A": {"A": "Pilate", "B": "Eyewitnesses", "C": "Herod", "D": "Pharisees"},
    "correct": "B"
  }
]
```

Run from the repository root:

```bash
export OPENAI_API_KEY=...
python evaluation/scripts/translate_llm_qa_to_chinese.py input.json evaluation/outputs/qa_zh.json
```

Use `--format native` to emit JSON that can be pasted into the admin QA importer:

```bash
python evaluation/scripts/translate_llm_qa_to_chinese.py input.json evaluation/outputs/qa_zh_native.json --format native
```

The compact output shape is:

```json
{"q_type": "open", "Q": "中文", "A": "中文"}
{"q_type": "mcq", "Q": "中文", "A": {"A": "中文", "B": "中文", "C": "中文", "D": "中文"}}
```

## Rescore existing responses (keywords)

Re-run per-language keyword scoring on stored transcript/text:

```bash
# By response id (print only)
python scripts/rescore_participant_responses.py YOUR_RESPONSE_ID

# Re-transcribe audio with Whisper, then score
python scripts/rescore_participant_responses.py --retranscribe --commit YOUR_RESPONSE_ID

# All responses for test user 2, save to DB
python scripts/rescore_participant_responses.py --participant "test user 2" --commit

# All responses for a QA item
python scripts/rescore_participant_responses.py --qa-item-id f4b6925b-e0a7-4154-8261-334c61676383
```

Requires `DATABASE_URL`, `OPENAI_API_KEY` (for `--retranscribe` or live audio ingest), and `pip install -e packages/eten-shared && pip install -r platform/requirements.txt && pip install -r message-bot/requirements.txt`.

Run commands from the **repository root**.

Define keywords per language on `/record` before expecting auto-scores.

## UW Luke 1:2 (content_id `174314`)

Source: `uw-translation-questions-eng-luke.json` — the Luke 1:2 eyewitnesses question.

Bundled copy: `supabase/seeds/data/uw_luke_1_2_174314.json`  
Full combo file (auto-detected if present):

`~/bible translation/ETEN-Bible-translation-project/v3/combo/uw-translation-questions-eng-luke.json`

### 1. Ensure database tables exist

Run `supabase/schema.sql` in Supabase SQL Editor if you have not already.

### 2. Seed the QA item (pick one)

**SQL** — `supabase/seeds/uw_luke_1_2_qa_item.sql`

**Python** — from repo root:

```bash
python scripts/test_luke_1_1_assignment.py --seed-only
```

Use another UW row from the combo JSON:

```bash
python scripts/test_luke_1_1_assignment.py --seed-only --content-id 174315 --json-path "/Users/louiscao/bible translation/ETEN-Bible-translation-project/v3/combo/uw-translation-questions-eng-luke.json"
```

### 3. Assign to a test participant (no WhatsApp send)

```bash
python scripts/test_luke_assignment.py
```

Participant language is set to `eng` to match the UW JSON.

### 3b. Use an existing QA item in Supabase (no UW JSON file)

```bash
# By UW content_id → passage_id uw-174345
python scripts/test_luke_assignment.py --from-db --content-id 174345 --assign \
  --wa-id 15551234567 --name "Test User 3"

# By passage_id or qa_items.id (from /qa-items)
python scripts/test_luke_assignment.py --from-db --passage-id uw-174345 --assign
python scripts/test_luke_assignment.py --from-db --qa-item-id YOUR-UUID --assign --answer "..."
```

`--from-db` only loads metadata from Postgres. Add `--assign` to give that specific question to the participant (requires an expert recording for their language). Without `--assign`, the script still auto-picks the next eligible question.

### 4. Optional — record a test answer

```bash
python scripts/test_luke_assignment.py --answer "The eyewitnesses were with the apostles from the beginning of Jesus ministry"
```

### 5. Verify in admin UI

`http://localhost:7860/qa-items` → click **Luke 1:2**

Set Chinese keywords on `http://localhost:7860/record?language=chinese`.

## Admin UI: add / remove QA items

On `/qa-items` (admin login required):

- **Add:** paste UW JSON or upload `uw-translation-questions-eng-luke.json` (single object or array)
- **Delete:** use **Delete** on a row or on the question detail page

UW format matches `supabase/seeds/data/uw_luke_1_2_174314.json`. Duplicate `passage_id` values are skipped when the checkbox is enabled.

Optional on each entry (UW or native): `passage_text` — the scripture text for `passage_reference` (e.g. Luke 2:3). Stored on `qa_items.passage_text`.

## Files

| File | Purpose |
|------|---------|
| `supabase/seeds/data/uw_luke_1_2_174314.json` | Bundled UW entry |
| `supabase/seeds/uw_luke_1_2_qa_item.sql` | SQL insert |
| `scripts/uw_qa_content.py` | Parse UW HTML → QA item fields |
| `scripts/test_luke_assignment.py` | Seed + assign + optional answer |

Legacy Genesis-style seed: `supabase/seeds/luke_1_1_qa_item.sql` (optional delete: `passage_id = 'luke-1-1'`).

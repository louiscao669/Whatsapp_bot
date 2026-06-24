# eten-shared

Shared Python package used by `message-bot` and `platform`:

- `models.py`, `database.py` — Supabase Postgres ORM
- `media_storage.py` — Supabase Storage + WhatsApp media fetch
- `mcq.py`, `keyword_matching.py`, `qa_keywords.py`, `transcription.py` — scoring
- `recordings.py`, `languages.py`, `keyword_parsing.py`
- `domain/` — assignment DB logic, QA eligibility, reminder rows, batch schedules

Install editable from the repo root:

```bash
pip install -e packages/eten-shared
```

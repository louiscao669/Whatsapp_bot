# Frontend (React + Vite)

Admin SPA for the ETEN WhatsApp bot. In production, Flask serves `dist/` on port **7860**; during development you can use Vite HMR on port **5173**.

## Run locally (dev)

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

Vite proxies `/api` and `/admin` to the **platform** on port **7860**, and `/webhook` to the **whatsapp-bot** on port **7861**. Start both first:

```bash
# from repository root
pip install -e ./packages/eten-shared
pip install -r platform/requirements.txt
pip install -r whatsapp-bot/requirements.txt
python platform/app.py    # terminal 1
python whatsapp-bot/app.py  # terminal 2
```

## Production build

```bash
cd frontend
npm run build
```

Then start the platform — it serves `frontend/dist/` and handles SPA routing:

```bash
python platform/app.py
```

Open http://localhost:7860

Legacy `/admin/*` URLs redirect to the SPA. `/admin/media/*` redirects to `/api/v1/media/*`.

## Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Dev server with HMR |
| `npm run build` | Production build → `dist/` |
| `npm run preview` | Preview production build |

## API endpoints used

| Endpoint | Purpose |
|----------|---------|
| `POST /api/v1/auth/*` | Login, logout, session |
| `GET /api/v1/auth/me` | Current user + nav |
| `GET /api/v1/media/*` | Authenticated audio streaming |
| `GET /api/v1/qa-items` | QA items list |
| `GET /api/v1/qa-items/:id` | QA item overview |
| `GET /api/v1/qa-items/:id/stats` | Response statistics |
| `GET /api/v1/qa-items/:id/responses` | Responses table |
| `GET /api/v1/qa-items/:id/assignments` | Assignments table |
| `POST/PATCH/DELETE /api/v1/qa-items/*` | Import, bulk, settings, assign, delete |
| `GET /api/v1/review-qa?tab=` | Review QA dashboard |
| `POST/PATCH /api/v1/review-qa/*` | Review QA mutations |
| `GET /api/v1/review-response` | Flagged response review queue |
| `POST /api/v1/review-response/:id/decision` | Mark correct/incorrect |
| `GET /api/v1/record?language=` | Record dashboard |
| `POST /api/v1/record/upload` | Upload recordings |
| `DELETE /api/v1/record/recordings/:id` | Remove recording |
| `GET /api/v1/analytics` | Analytics dashboard |
| `GET /api/v1/participants` | Participants list |
| `GET /api/v1/participants/:id` | Participant detail |
| `GET/POST/DELETE /api/v1/system-languages` | Language registry |
| `GET /api/v1/export/audio` | Audio export browser |
| `GET /api/v1/export/audio/:id` | Single audio download |
| `POST /api/v1/export/audio/download` | ZIP download |
| `GET /api/v1/export/responses.csv` | All responses CSV |
| `GET /api/v1/export/flagged.csv` | Flagged responses CSV |

Session cookies are sent via `credentials: 'include'`. For local HTTP dev, set `SESSION_COOKIE_SECURE=false` in `.env` if login cookies are not persisted.

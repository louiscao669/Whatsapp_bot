# Frontend (React + Vite)

Admin SPA for the ETEN WhatsApp bot. Being built incrementally; the legacy UI remains on the Flask backend at `/admin` until each screen is migrated.

## Run locally

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

Vite proxies `/admin`, `/webhook`, and `/api` to the Flask backend on port **7860**. Start the backend first:

```bash
# from repository root
python backend/app.py
```

## Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Dev server with HMR |
| `npm run build` | Production build → `dist/` |
| `npm run preview` | Preview production build |

## Layout

```text
frontend/
  src/
    App.tsx       # root shell (screens added in later phases)
    main.tsx
  vite.config.ts  # dev proxy to backend
```

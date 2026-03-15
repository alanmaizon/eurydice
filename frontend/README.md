# Frontend

This frontend is now a Vite-based React console for the Ancient Greek Live Tutor. The UI still follows the official live-api web console structure, but the transport is no longer browser-to-Gemini. It talks to the local tutor backend over `/api/runtime` and `/ws/live`.

## Stack

- React 18
- TypeScript
- Vite 8
- Vitest
- Sass

## Node baseline

- Node `22.12+`
- npm `10+`

Use the repo-level `.nvmrc` if you want a quick local switch:

```bash
nvm use
```

## Local development

Start the backend first:

```bash
PYTHONPATH=. python3 -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Then run the frontend:

```bash
cd frontend
cp .env.example .env
npm install
npm start
```

The Vite dev server runs at `http://localhost:3000` and proxies backend requests and websocket traffic to `http://127.0.0.1:8000`.

## Environment

Only a small set of client-side overrides are supported:

```bash
VITE_API_BASE_URL=http://localhost:8000
# Local development only:
# VITE_GEMINI_API_KEY=your-local-gemini-api-key
# Optional:
# VITE_RUNTIME_URL=http://localhost:8000/api/runtime
# VITE_LIVE_WS_URL=ws://localhost:8000/ws/live
```

If these are omitted during local development, Vite proxying handles `/api/*`, `/health*`, and `/ws/*`.
If `VITE_GEMINI_API_KEY` is set in local development, the frontend forwards it
to the backend during `client.hello` so the backend can still own Gemini Live,
tools, and session state.

## Scripts

```bash
npm start        # alias for vite dev
npm run dev      # vite dev
npm run build    # production build to dist/
npm run preview  # preview the dist build
npm run test     # vitest
npm run typecheck
```

## Current direction

- The center panel is now tutor-specific instead of the old Altair demo.
- The sidebar still behaves like a console/logger surface.
- The live client is a compatibility layer over the backend websocket contract.
- Mic and camera are intentionally secondary until the text loop is stable.

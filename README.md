# Ancient Greek Live Tutor

This repository is a fresh scaffold for a voice-first multimodal Ancient Greek tutor built around Gemini Live API, Google ADK, and Google Cloud. It is intentionally minimal: the goal is to provide a clean foundation for live tutoring work without carrying over the old Eurydice product logic.

## Why this scaffold looks this way

The prior codebase already proved out a sensible split:

- `frontend/` for a browser-based live session UI
- `backend/` for FastAPI APIs, live session orchestration, and Google integrations

This scaffold keeps that shape, while leaving the archival application under `legacy/` untouched.

## Repository layout

```text
vista/
├── cloudbuild/       # Cloud Build configs for infra provisioning and backend deploy
├── backend/          # FastAPI scaffold for session bootstrap, runtime info, and Gemini Live websocket bridge
├── docs/             # Product and architecture notes
├── frontend/         # Vite + React + TypeScript scaffold for the tutor session UI
├── infra/            # Deployment notes for future Google Cloud work
├── legacy/           # Archived Eurydice codebase
└── scripts/          # Small helper scripts for local development
```

## Current status

What exists now:

- A minimal live session UI prepared for microphone, camera, and worksheet image intake
- A FastAPI backend with runtime metadata, session bootstrap, and a Gemini Live-backed `/ws/live` bridge with scaffold fallback
- Skeletal agent layers for prompts, session state, tutoring modes, tool registry, Gemini Live planning, and ADK orchestration
- Deterministic starter tools for parsing, grading, and drill generation, wired into live tool calls
- An ADK policy graph seam at `client.turn.end` that chooses tool-preflight or direct-generation flow, with deterministic fallback when ADK cannot run
- Focused documentation explaining the intended architecture and next implementation steps

What is intentionally not implemented yet:

- ADK decision quality evaluation and guardrail tuning
- Persistent storage, auth, or full infrastructure-as-code coverage

## Local development

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Or use the helper scripts from the repo root:

```bash
./scripts/bootstrap-backend.sh
./scripts/dev-backend.sh
./scripts/dev-frontend.sh
```

For local Gemini Live sessions driven from the frontend, add `VITE_GEMINI_API_KEY` to `frontend/.env` and run the frontend with `npm start` so the Vite dev server forwards that key during `client.hello`.

For a calmer local loop while we stabilize the live agent, set `TUTOR_LIVE_BACKEND_PROFILE=simple` in `backend/.env`. That profile keeps session memory and local reference loading, skips the heavier orchestration path, and still uses Gemini Live native audio.

## Next steps

1. Add an evaluation harness for ADK policy graph decisions (coverage, regression checks, and safety guardrails).
2. Improve deterministic tools with richer morphology coverage and structured rubric outputs.
3. Add persistence for session state, learner progress, and uploaded worksheet metadata.
4. Decide on the first Google Cloud deployment slice, likely backend to Cloud Run and frontend to static hosting or a lightweight edge deploy.

For a more detailed breakdown, see `docs/product.md` and `docs/architecture.md`.
For the websocket message contract used by the current live bridge, see `docs/live-event-contract.md`.

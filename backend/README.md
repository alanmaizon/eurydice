# Backend Scaffold

The backend is a small FastAPI service that defines the first stable seams for the new Ancient Greek live tutor.

## Responsibilities in this scaffold

- expose a health endpoint and runtime metadata
- bootstrap a tutor session with mode, tools, and prompt preview
- bridge `/ws/live` events to Gemini Live using the shared contract in `backend/app/live/protocol.py`
- run a turn-end ADK policy graph seam (with deterministic fallback) for tool-preflight routing
- keep agent pieces separated so ADK and tool work can grow without reshaping the app

## Key modules

```text
backend/app/
├── api/                   # HTTP route registration and dependencies
├── agents/
│   ├── orchestration/     # ADK policy graph runtime + deterministic fallback
│   ├── tools/             # parse / grade / drill tool definitions
│   ├── modes.py           # tutoring mode definitions
│   ├── prompts.py         # system prompt builder
│   └── session_state.py   # session state snapshot scaffold
├── live/                  # Gemini Live integration planning layer
├── main.py                # FastAPI app and websocket bridge
├── schemas.py             # request / response models
└── settings.py            # env-driven configuration
```

## Endpoints

- `GET /health`
- `GET /api/runtime`
- `GET /api/live/modes`
- `POST /api/live/session`
- `WS /ws/live`

## Running locally

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

If you want the websocket to connect upstream to Gemini Live instead of scaffold fallback mode, set one of:

- `TUTOR_GEMINI_API_KEY`
- `GEMINI_API_KEY`
- `GOOGLE_API_KEY`

Or configure Vertex mode with `TUTOR_GOOGLE_CLOUD_PROJECT`.

For local debugging, the simplest path is the text-first live profile:

- `TUTOR_LIVE_BACKEND_PROFILE=simple`
- keeps session memory and reference loading
- skips ADK/tool orchestration on normal turns
- keeps Gemini Live native audio enabled while using the lighter turn pipeline

Switch back to `TUTOR_LIVE_BACKEND_PROFILE=full` when you want the heavier audio-first/tool-enabled path again.

For a project-owned local runtime instead of whichever global Python happens to be active, use:

```bash
./scripts/bootstrap-backend.sh
./scripts/dev-backend.sh
```

## What is still a stub

- ADK policy evaluation/guardrail harness and richer routing coverage
- deeper deterministic tool logic (current parse/grade/drill execution is intentionally lightweight)
- storage, auth, and session persistence
- production observability

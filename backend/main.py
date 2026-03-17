from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from config import settings, USE_MOCK
from session import handle_websocket

app = FastAPI(title="Logos Backend", version="1.0.0")

# CORS
origins = [o.strip() for o in settings.allowed_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "mock_mode": USE_MOCK}


@app.get("/metrics")
async def metrics() -> dict:
    from telemetry import get_collector
    c = get_collector()
    return {
        "product": c.compute_product_metrics(),
        "tool_quality": c.compute_tool_quality_metrics(),
    }


@app.get("/metrics/session/{session_id}")
async def session_metrics(session_id: str) -> dict:
    from telemetry import get_collector
    return get_collector().compute_session_metrics(session_id)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        await handle_websocket(websocket)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            import json
            await websocket.send_text(
                json.dumps({"type": "error", "message": str(exc)})
            )
        except Exception:
            pass

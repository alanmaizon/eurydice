"""
Session lifecycle management.

Each WebSocket connection gets one Session object which tracks state and
routes messages to either mock or live Gemini handler.
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from config import USE_MOCK


@dataclass
class Session:
    session_id: str = field(default_factory=lambda: f"s-{uuid.uuid4().hex[:8]}")
    is_active: bool = False
    config: dict[str, Any] = field(default_factory=dict)
    _handler_task: Optional[asyncio.Task] = field(default=None, repr=False)

    def mark_active(self) -> None:
        self.is_active = True

    def mark_ended(self) -> None:
        self.is_active = False
        if self._handler_task and not self._handler_task.done():
            self._handler_task.cancel()


async def handle_websocket(websocket: Any) -> None:
    """
    Top-level WebSocket handler. Reads the first 'session.start' message,
    then delegates to mock or live mode.
    """
    try:
        raw = await websocket.receive_text()
        first_msg = json.loads(raw)
    except Exception:
        return

    if first_msg.get("type") != "session.start":
        # Reject malformed first message
        await websocket.send_text(
            json.dumps({"type": "error", "message": "Expected session.start as first message"})
        )
        return

    config = first_msg.get("config", {})

    if USE_MOCK:
        from mock_mode import handle_mock_session

        # Feed the session.start message, then loop on subsequent messages
        await handle_mock_session(websocket, first_msg)
        while True:
            try:
                raw = await websocket.receive_text()
                msg = json.loads(raw)
                await handle_mock_session(websocket, msg)
                if msg.get("type") == "session.end":
                    break
            except Exception:
                break
    else:
        from gemini_client import run_gemini_session
        await run_gemini_session(websocket, config)

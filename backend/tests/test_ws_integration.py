"""
WebSocket integration tests — mock mode.

Exercises the full WS transport layer through FastAPI's TestClient:
  session lifecycle, text streaming, tool-call flow, error handling.

Run:
    cd backend && python -m pytest tests/test_ws_integration.py -v
"""

import json
import pytest
from unittest.mock import patch
from starlette.testclient import TestClient

from main import app


# ── Helpers ──────────────────────────────────────────────────────────────────


def _recv_turn(ws, *, stop_on: str = "log", max_msgs: int = 500) -> list[dict]:
    """
    Read messages from the WS until a message with type == stop_on arrives.

    The mock handler always ends each interaction with a known terminal message:
      - Handshake → log (event=session.started)
      - Text/tool response → log (event=output.done)
      - Session end → status (state=ended) — use stop_on="status"
      - Interrupt → log (event=input.interrupt)
    """
    msgs: list[dict] = []
    for _ in range(max_msgs):
        raw = ws.receive_text()
        msg = json.loads(raw)
        msgs.append(msg)
        if msg.get("type") == stop_on:
            break
    return msgs


def _find(msgs: list[dict], msg_type: str) -> dict | None:
    return next((m for m in msgs if m.get("type") == msg_type), None)


def _find_all(msgs: list[dict], msg_type: str) -> list[dict]:
    return [m for m in msgs if m.get("type") == msg_type]


@pytest.fixture(autouse=True)
def _force_mock():
    """Patch USE_MOCK=True in session.py so the mock handler is used."""
    with patch("session.USE_MOCK", True), patch("session.USE_CLAUDE", False):
        yield


def _handshake(ws) -> list[dict]:
    """Send session.start and drain the handshake messages."""
    ws.send_json({"type": "session.start", "config": {}})
    return _recv_turn(ws, stop_on="log")


@pytest.fixture
def ws():
    """Open a WebSocket, perform handshake, yield the live socket."""
    with TestClient(app).websocket_connect("/ws") as socket:
        handshake = _handshake(socket)
        assert _find(handshake, "session.started") is not None
        yield socket


# ── Health check ─────────────────────────────────────────────────────────────


class TestHealthEndpoint:
    def test_health_returns_ok(self):
        resp = TestClient(app).get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ── Session lifecycle ────────────────────────────────────────────────────────


class TestSessionLifecycle:
    def test_session_start_handshake(self):
        with TestClient(app).websocket_connect("/ws") as socket:
            msgs = _handshake(socket)
            types = [m["type"] for m in msgs]
            assert "status" in types
            assert "session.started" in types
            live = next(
                (m for m in msgs if m.get("type") == "status" and m.get("state") == "live"),
                None,
            )
            assert live is not None

    def test_session_start_returns_session_id(self):
        with TestClient(app).websocket_connect("/ws") as socket:
            msgs = _handshake(socket)
            started = _find(msgs, "session.started")
            assert started is not None
            assert started["session_id"].startswith("mock-")

    def test_session_end(self, ws):
        ws.send_json({"type": "session.end"})
        msgs = _recv_turn(ws, stop_on="status")
        assert _find(msgs, "session.ended") is not None
        status = _find(msgs, "status")
        assert status["state"] == "ended"

    def test_bad_first_message_rejected(self):
        with TestClient(app).websocket_connect("/ws") as socket:
            socket.send_json({"type": "input.text", "text": "hello"})
            msgs = _recv_turn(socket, stop_on="error")
            error = _find(msgs, "error")
            assert error is not None
            assert "session.start" in error.get("message", "").lower()


# ── Text input → streaming response ─────────────────────────────────────────


class TestTextStreaming:
    def test_text_input_returns_deltas_and_done(self, ws):
        ws.send_json({"type": "input.text", "text": "hello"})
        msgs = _recv_turn(ws)

        deltas = _find_all(msgs, "output.text.delta")
        done = _find(msgs, "output.text.done")
        assert len(deltas) > 0, "Expected streaming text deltas"
        assert done is not None, "Expected text.done message"
        assert len(done["full_text"]) > 0

    def test_streaming_text_accumulates_correctly(self, ws):
        ws.send_json({"type": "input.text", "text": "hello"})
        msgs = _recv_turn(ws)

        deltas = _find_all(msgs, "output.text.delta")
        done = _find(msgs, "output.text.done")
        accumulated = "".join(d["delta"] for d in deltas)
        assert accumulated == done["full_text"]

    def test_different_inputs_get_different_responses(self, ws):
        ws.send_json({"type": "input.text", "text": "hello"})
        msgs1 = _recv_turn(ws)
        done1 = _find(msgs1, "output.text.done")

        ws.send_json({"type": "input.text", "text": "How do you pronounce ἄνθρωπος?"})
        msgs2 = _recv_turn(ws)
        done2 = _find(msgs2, "output.text.done")

        assert done1["full_text"] != done2["full_text"]


# ── Tool call flow ───────────────────────────────────────────────────────────


class TestToolCallFlow:
    def test_parse_triggers_tool_call(self, ws):
        ws.send_json({"type": "input.text", "text": "parse μῆνιν"})
        msgs = _recv_turn(ws)

        tool_call = _find(msgs, "tool.call")
        tool_result = _find(msgs, "tool.result")
        assert tool_call is not None, "Expected a tool.call message"
        assert tool_call["tool_name"] == "parse_greek"
        assert tool_result is not None, "Expected a tool.result message"
        assert "word" in tool_result.get("result", {})

    def test_scan_meter_triggers_tool_call(self, ws):
        # Avoid μῆνιν (iliad trigger) and "this" ("hi" substring triggers hello)
        ws.send_json({"type": "input.text", "text": "scan the hexameter rhythm of a verse"})
        msgs = _recv_turn(ws)

        tool_call = _find(msgs, "tool.call")
        assert tool_call is not None
        assert tool_call["tool_name"] == "scan_meter"

        tool_result = _find(msgs, "tool.result")
        assert tool_result is not None
        result = tool_result["result"]
        assert "meter" in result
        assert "pattern" in result

    def test_lexicon_lookup_triggers_tool_call(self, ws):
        ws.send_json({"type": "input.text", "text": "look up λόγος in the lexicon"})
        msgs = _recv_turn(ws)

        tool_call = _find(msgs, "tool.call")
        assert tool_call is not None
        assert tool_call["tool_name"] == "lookup_lexicon"

    def test_tool_call_has_matching_call_id(self, ws):
        ws.send_json({"type": "input.text", "text": "parse εἰμί"})
        msgs = _recv_turn(ws)

        tool_call = _find(msgs, "tool.call")
        tool_result = _find(msgs, "tool.result")
        assert tool_call is not None
        assert "call_id" in tool_call
        assert tool_call["call_id"].startswith("call-")
        assert tool_result["call_id"] == tool_call["call_id"]


# ── Input types ──────────────────────────────────────────────────────────────


class TestInputTypes:
    def test_audio_input_returns_response(self, ws):
        ws.send_json({"type": "input.audio", "audio": "fake-base64"})
        msgs = _recv_turn(ws)
        done = _find(msgs, "output.text.done")
        assert done is not None

    def test_image_input_returns_response(self, ws):
        ws.send_json({"type": "input.image", "image": "fake-base64"})
        msgs = _recv_turn(ws)
        done = _find(msgs, "output.text.done")
        assert done is not None

    def test_interrupt_acknowledged(self, ws):
        ws.send_json({"type": "input.interrupt"})
        msgs = _recv_turn(ws, stop_on="log")
        log = _find(msgs, "log")
        assert log is not None
        assert log["event"] == "input.interrupt"


# ── Protocol robustness ─────────────────────────────────────────────────────


class TestProtocolRobustness:
    def test_multiple_messages_in_sequence(self, ws):
        for text in ["hello", "parse εἰμί", "What is Greek?"]:
            ws.send_json({"type": "input.text", "text": text})
            msgs = _recv_turn(ws)
            done = _find(msgs, "output.text.done")
            assert done is not None, f"No done message for: {text}"

    def test_response_includes_log_events(self, ws):
        ws.send_json({"type": "input.text", "text": "hello"})
        msgs = _recv_turn(ws)
        logs = _find_all(msgs, "log")
        assert len(logs) > 0
        events = [lg["event"] for lg in logs]
        assert "output.done" in events

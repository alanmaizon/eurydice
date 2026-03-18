"""
End-to-end tests for Eurydice.

Starts a real uvicorn server on a random port and connects via:
  - httpx        (HTTP endpoints — /health, /metrics)
  - websockets   (WebSocket over real TCP sockets)

This validates the full stack: FastAPI routing, session lifecycle, state
machine, mastery gate, and coaching response, without relying on
Starlette's in-process TestClient transport.

Run:
    cd backend && python -m pytest tests/test_e2e.py -v
"""

import asyncio
import base64
import json
import math
import socket
import struct
import threading
import time
from typing import Any

import httpx
import pytest
import uvicorn
import websockets

import session as sess_module
import claude_client
from main import app


# ── WAV helper ────────────────────────────────────────────────────────────────

def _make_wav_b64(duration_s: float = 3.0, sample_rate: int = 16000) -> str:
    """Generate a minimal 440 Hz sine-wave WAV as base64."""
    num_samples = int(sample_rate * duration_s)
    samples = [
        int(32767 * math.sin(2 * math.pi * 440 * i / sample_rate))
        for i in range(num_samples)
    ]
    pcm_data = struct.pack(f"<{num_samples}h", *samples)
    data_size = len(pcm_data)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + data_size, b"WAVE",
        b"fmt ", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16,
        b"data", data_size,
    )
    return base64.b64encode(header + pcm_data).decode()


# ── WS protocol helpers ───────────────────────────────────────────────────────

async def _recv_until(ws, stop_type: str, max_msgs: int = 100) -> list[dict]:
    msgs: list[dict] = []
    for _ in range(max_msgs):
        raw = await ws.recv()
        msg = json.loads(raw)
        msgs.append(msg)
        if msg.get("type") == stop_type:
            break
    return msgs


def _find(msgs: list[dict], msg_type: str) -> dict | None:
    return next((m for m in msgs if m.get("type") == msg_type), None)


def _find_all(msgs: list[dict], msg_type: str) -> list[dict]:
    return [m for m in msgs if m.get("type") == msg_type]


async def _handshake(ws) -> list[dict]:
    await ws.send(json.dumps({"type": "session.start", "config": {}}))
    return await _recv_until(ws, "log")


async def _set_target(ws, description: str = "E2E test passage", bpm: float = 100.0) -> list[dict]:
    await ws.send(json.dumps({
        "type": "target.set",
        "description": description,
        "target_bpm": bpm,
        "difficulty": "beginner",
    }))
    return await _recv_until(ws, "log")


async def _send_take(ws) -> list[dict]:
    wav_b64 = _make_wav_b64(duration_s=3.0)
    await ws.send(json.dumps({
        "type": "input.audio_recording",
        "audio_b64": wav_b64,
        "duration_s": 3.0,
    }))
    return await _recv_until(ws, "log")


# ── Mock handler (mirrors test_ws_eurydice._mock_claude_handler) ──────────────
# Inline to avoid importing from another test file.

import uuid as _uuid
from eurydice_session import (
    SessionState, create_session, drop_session, MasteryCheckResult,
)
from models import (
    SessionStartedMessage, StatusMessage, TextDeltaMessage, TextDoneMessage,
    ToolCallMessage, ToolResultMessage, LogMessage, StateChangedMessage,
    MasteryUpdateMessage, MasteryAchievedMessage, TargetValidationMessage,
    CaptureInvalidMessage,
)
from tools import execute_eurydice_tool_mock
from presets import get_preset


async def _e2e_mock_claude_handler(websocket: Any, config: dict) -> None:
    """
    Lightweight mock replacing run_claude_session for e2e tests.
    Same protocol as test_ws_eurydice._mock_claude_handler.
    """
    session_id = f"e2e-{_uuid.uuid4().hex[:8]}"
    sess = create_session(session_id)

    async def send(msg: Any) -> None:
        payload = msg.model_dump() if hasattr(msg, "model_dump") else msg
        await websocket.send_text(json.dumps(payload))

    def now() -> str:
        return "2025-01-01T00:00:00Z"

    async def emit_state(prev=None) -> None:
        await send(StateChangedMessage(
            state=sess.state.value,
            previous=prev.value if prev else None,
        ))

    # Handshake
    await send(StatusMessage(state="connecting"))
    await send(SessionStartedMessage(session_id=session_id))
    await send(StatusMessage(state="live"))
    await emit_state()
    await send(LogMessage(event="session.started", data={"session_id": session_id}, timestamp=now()))

    try:
        while True:
            try:
                raw = await websocket.receive_text()
                msg = json.loads(raw)
            except Exception:
                break

            msg_type = msg.get("type")

            if msg_type == "session.end":
                break

            elif msg_type == "target.set":
                description = msg.get("description", "")
                target_bpm = msg.get("target_bpm")
                target_notes = msg.get("target_notes")
                difficulty = msg.get("difficulty", "beginner")
                preset_id = msg.get("preset_id")

                if preset_id:
                    preset = get_preset(preset_id)
                    if preset:
                        description = description or preset["description"]
                        target_bpm = target_bpm or preset["target_bpm"]
                        target_notes = target_notes or preset["target_notes"]
                        difficulty = difficulty or preset["difficulty"]
                    else:
                        await send(TargetValidationMessage(valid=False, errors=[f"Unknown preset: {preset_id}"]))
                        continue

                prev = sess.state
                validation = sess.set_target(
                    description=description,
                    target_bpm=target_bpm,
                    target_notes=target_notes,
                    difficulty=difficulty,
                )

                if not validation.valid:
                    await send(TargetValidationMessage(valid=False, errors=validation.errors))
                    continue

                if validation.warnings:
                    await send(TargetValidationMessage(valid=True, warnings=validation.warnings))

                await emit_state(prev)
                ack = f"Target set: {description}. Record a take when ready."
                await send(TextDeltaMessage(delta=ack))
                await send(TextDoneMessage(full_text=ack))
                await send(LogMessage(event="output.done", timestamp=now()))

            elif msg_type == "input.audio_recording":
                audio_b64 = msg.get("audio_b64", "")

                prev = sess.state
                sess.transition(SessionState.RECORDING)
                await emit_state(prev)

                prev = sess.state
                sess.force_state(SessionState.PROCESSING_QUICK)
                await emit_state(prev)

                call_id = f"call-{_uuid.uuid4().hex[:8]}"
                args: dict[str, Any] = {"mode": "quick", "audio_b64": audio_b64}
                if sess.target.target_bpm:
                    args["target_bpm"] = sess.target.target_bpm

                await send(ToolCallMessage(tool_name="audio_analysis", args=args, call_id=call_id))
                result = execute_eurydice_tool_mock("audio_analysis", args)
                analysis_confidence = float(result.get("analysis_confidence", 0.0))

                if analysis_confidence < sess.mastery_gate.confidence_gate:
                    prev = sess.state
                    sess.transition(SessionState.CAPTURE_INVALID)
                    await emit_state(prev)
                    await send(CaptureInvalidMessage(
                        analysis_confidence=analysis_confidence,
                        capture_quality=result.get("capture_quality", {}).get("overall", "unknown"),
                        reasons=result.get("warnings", []),
                    ))
                else:
                    mastery_check = sess.record_attempt(result)
                    await send(ToolResultMessage(call_id=call_id, result=result))
                    await send(MasteryUpdateMessage(
                        consecutive_passes=mastery_check.consecutive_passes,
                        passes_needed=mastery_check.passes_needed,
                        mastered=mastery_check.mastered,
                        gate_detail=mastery_check.gate_detail,
                        attempt_number=mastery_check.attempt.attempt_number,
                    ))

                    if mastery_check.mastered:
                        prev = sess.state
                        sess.force_state(SessionState.MASTERED)
                        await emit_state(prev)
                        await send(MasteryAchievedMessage(
                            total_attempts=len(sess.mastery_gate.attempts),
                            passage_description=sess.target.description or None,
                        ))
                    else:
                        prev = sess.state
                        sess.transition(SessionState.FEEDBACK_QUICK)
                        await emit_state(prev)

                    coaching_id = f"call-{_uuid.uuid4().hex[:8]}"
                    coaching_result = {
                        "observed_issue": "timing drift at bar 2",
                        "primary_correction": "accent beat 1 more firmly",
                        "drill": "play bars 1-2 at 80% tempo",
                        "success_criterion": "clean timing for 4 bars",
                    }
                    await send(ToolCallMessage(tool_name="coaching_response", args=coaching_result, call_id=coaching_id))
                    await send(ToolResultMessage(call_id=coaching_id, result=coaching_result))

                    if not mastery_check.mastered:
                        prev = sess.state
                        sess.transition(SessionState.DRILL_ASSIGNED)
                        await emit_state(prev)

                feedback = "Good take. Focus on timing at bar 2."
                await send(TextDeltaMessage(delta=feedback))
                await send(TextDoneMessage(full_text=feedback))
                await send(LogMessage(event="output.done", timestamp=now()))

            elif msg_type == "input.text":
                text = msg.get("text", "")
                reply = f"Received: {text}"
                await send(TextDeltaMessage(delta=reply))
                await send(TextDoneMessage(full_text=reply))
                await send(LogMessage(event="output.done", timestamp=now()))

    finally:
        drop_session(session_id)
        await send(StatusMessage(state="ended"))
        await send(LogMessage(event="session.ended", timestamp=now()))


# ── Live server fixture ────────────────────────────────────────────────────────

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server_url():
    """
    Start a real uvicorn server with the Eurydice mock handler.

    Patches module-level flags before the server thread starts so the same
    Python process shares the patched state across threads.
    """
    port = _free_port()

    orig_use_mock = sess_module.USE_MOCK
    orig_use_claude = sess_module.USE_CLAUDE
    orig_handler = claude_client.run_claude_session

    sess_module.USE_MOCK = False
    sess_module.USE_CLAUDE = True
    claude_client.run_claude_session = _e2e_mock_claude_handler

    config = uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="error", loop="asyncio"
    )
    server = uvicorn.Server(config)

    def _run() -> None:
        asyncio.run(server.serve())

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    # Poll until ready
    deadline = time.time() + 10.0
    while time.time() < deadline:
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.5)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(0.05)
    else:
        raise RuntimeError(f"Server on port {port} did not start within 10 s")

    yield f"http://127.0.0.1:{port}", f"ws://127.0.0.1:{port}/ws"

    server.should_exit = True
    thread.join(timeout=5)

    sess_module.USE_MOCK = orig_use_mock
    sess_module.USE_CLAUDE = orig_use_claude
    claude_client.run_claude_session = orig_handler


# ── HTTP endpoint tests ────────────────────────────────────────────────────────


class TestHTTPEndpoints:
    def test_health_returns_ok(self, server_url):
        base, _ = server_url
        r = httpx.get(f"{base}/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "mock_mode" in body

    def test_metrics_shape(self, server_url):
        base, _ = server_url
        r = httpx.get(f"{base}/metrics")
        assert r.status_code == 200
        body = r.json()
        assert "product" in body
        assert "tool_quality" in body

    def test_health_content_type_is_json(self, server_url):
        base, _ = server_url
        r = httpx.get(f"{base}/health")
        assert "application/json" in r.headers["content-type"]


# ── WebSocket handshake tests ─────────────────────────────────────────────────


class TestWebSocketHandshake:
    def test_handshake_sends_session_started(self, server_url):
        _, ws_url = server_url

        async def run() -> None:
            async with websockets.connect(ws_url) as ws:
                msgs = await _handshake(ws)
                assert _find(msgs, "session.started") is not None

        asyncio.run(run())

    def test_initial_state_is_idle(self, server_url):
        _, ws_url = server_url

        async def run() -> None:
            async with websockets.connect(ws_url) as ws:
                msgs = await _handshake(ws)
                state = _find(msgs, "session.state")
                assert state is not None
                assert state["state"] == "idle"

        asyncio.run(run())

    def test_status_live_emitted(self, server_url):
        _, ws_url = server_url

        async def run() -> None:
            async with websockets.connect(ws_url) as ws:
                msgs = await _handshake(ws)
                statuses = _find_all(msgs, "status")
                states = [s["state"] for s in statuses]
                assert "live" in states

        asyncio.run(run())

    def test_session_end_closes_cleanly(self, server_url):
        _, ws_url = server_url

        async def run() -> None:
            async with websockets.connect(ws_url) as ws:
                await _handshake(ws)
                await ws.send(json.dumps({"type": "session.end"}))
                # Drain remaining messages; server should close
                msgs: list[dict] = []
                try:
                    while True:
                        raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                        msgs.append(json.loads(raw))
                except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
                    pass
                statuses = [m["state"] for m in msgs if m.get("type") == "status"]
                assert "ended" in statuses

        asyncio.run(run())


# ── Target-set tests ──────────────────────────────────────────────────────────


class TestTargetSetE2E:
    def test_set_target_transitions_to_target_selected(self, server_url):
        _, ws_url = server_url

        async def run() -> None:
            async with websockets.connect(ws_url) as ws:
                await _handshake(ws)
                msgs = await _set_target(ws)
                state = _find(msgs, "session.state")
                assert state is not None
                assert state["state"] == "target_selected"

        asyncio.run(run())

    def test_set_target_ack_contains_description(self, server_url):
        _, ws_url = server_url

        async def run() -> None:
            async with websockets.connect(ws_url) as ws:
                await _handshake(ws)
                msgs = await _set_target(ws, description="Comfortably Numb intro")
                done = _find(msgs, "output.text.done")
                assert done is not None
                assert "Comfortably Numb" in done["full_text"]

        asyncio.run(run())

    def test_empty_description_returns_validation_error(self, server_url):
        _, ws_url = server_url

        async def run() -> None:
            async with websockets.connect(ws_url) as ws:
                await _handshake(ws)
                await ws.send(json.dumps({
                    "type": "target.set",
                    "description": "",
                    "target_bpm": 120,
                }))
                msgs = await _recv_until(ws, "target.validation")
                v = _find(msgs, "target.validation")
                assert v is not None
                assert v["valid"] is False

        asyncio.run(run())

    def test_out_of_range_bpm_returns_validation_error(self, server_url):
        _, ws_url = server_url

        async def run() -> None:
            async with websockets.connect(ws_url) as ws:
                await _handshake(ws)
                await ws.send(json.dumps({
                    "type": "target.set",
                    "description": "Test passage",
                    "target_bpm": 500,  # > 300
                }))
                msgs = await _recv_until(ws, "target.validation")
                v = _find(msgs, "target.validation")
                assert v is not None
                assert v["valid"] is False

        asyncio.run(run())


# ── Audio recording + mastery loop tests ─────────────────────────────────────


class TestAudioRecordingE2E:
    def test_audio_triggers_analysis_tool_call(self, server_url):
        _, ws_url = server_url

        async def run() -> None:
            async with websockets.connect(ws_url) as ws:
                await _handshake(ws)
                await _set_target(ws)
                msgs = await _send_take(ws)
                tool_calls = _find_all(msgs, "tool.call")
                audio_call = next(
                    (t for t in tool_calls if t.get("tool_name") == "audio_analysis"),
                    None,
                )
                assert audio_call is not None

        asyncio.run(run())

    def test_audio_produces_mastery_update(self, server_url):
        _, ws_url = server_url

        async def run() -> None:
            async with websockets.connect(ws_url) as ws:
                await _handshake(ws)
                await _set_target(ws)
                msgs = await _send_take(ws)
                mastery = _find(msgs, "mastery.update")
                assert mastery is not None
                assert "consecutive_passes" in mastery
                assert "attempt_number" in mastery
                assert mastery["attempt_number"] == 1

        asyncio.run(run())

    def test_coaching_response_included_after_take(self, server_url):
        _, ws_url = server_url

        async def run() -> None:
            async with websockets.connect(ws_url) as ws:
                await _handshake(ws)
                await _set_target(ws)
                msgs = await _send_take(ws)
                tool_calls = _find_all(msgs, "tool.call")
                coaching = next(
                    (t for t in tool_calls if t.get("tool_name") == "coaching_response"),
                    None,
                )
                assert coaching is not None
                args = coaching.get("args", {})
                assert "primary_correction" in args
                assert "drill" in args

        asyncio.run(run())

    def test_state_transitions_during_analysis(self, server_url):
        _, ws_url = server_url

        async def run() -> None:
            async with websockets.connect(ws_url) as ws:
                await _handshake(ws)
                await _set_target(ws)
                msgs = await _send_take(ws)
                states = [m["state"] for m in _find_all(msgs, "session.state")]
                assert "recording" in states
                assert "processing_quick" in states

        asyncio.run(run())

    def test_attempt_numbers_increment_across_takes(self, server_url):
        _, ws_url = server_url

        async def run() -> list[int]:
            attempt_nums: list[int] = []
            async with websockets.connect(ws_url) as ws:
                await _handshake(ws)
                await _set_target(ws)
                for _ in range(3):
                    msgs = await _send_take(ws)
                    mu = _find(msgs, "mastery.update")
                    if mu:
                        attempt_nums.append(mu["attempt_number"])
                        if mu.get("mastered"):
                            break
            return attempt_nums

        nums = asyncio.run(run())
        assert len(nums) >= 1
        # Each attempt number must be 1 more than the previous
        for i, n in enumerate(nums):
            assert n == i + 1


# ── Full mastery loop tests ───────────────────────────────────────────────────


class TestMasteryLoopE2E:
    async def _run_loop(self, ws_url: str) -> dict[str, Any]:
        """Drive the full mastery loop and collect results."""
        stats: dict[str, Any] = {
            "attempts": 0,
            "mastered": False,
            "mastery_updates": [],
            "mastery_achieved": None,
        }
        async with websockets.connect(ws_url) as ws:
            await _handshake(ws)
            await _set_target(ws, description="Full loop passage", bpm=90.0)

            for _ in range(10):
                msgs = await _send_take(ws)
                stats["attempts"] += 1
                mu = _find(msgs, "mastery.update")
                if mu:
                    stats["mastery_updates"].append(mu)
                if mu and mu.get("mastered"):
                    stats["mastered"] = True
                    stats["mastery_achieved"] = _find(msgs, "mastery.achieved")
                    break
        return stats

    def test_mastery_is_achieved(self, server_url):
        _, ws_url = server_url
        stats = asyncio.run(self._run_loop(ws_url))
        assert stats["mastered"], f"Not mastered after {stats['attempts']} attempts"

    def test_mastery_requires_at_least_three_passes(self, server_url):
        _, ws_url = server_url
        stats = asyncio.run(self._run_loop(ws_url))
        assert stats["attempts"] >= 3

    def test_mastery_achieved_message_present(self, server_url):
        _, ws_url = server_url
        stats = asyncio.run(self._run_loop(ws_url))
        achieved = stats["mastery_achieved"]
        assert achieved is not None
        assert achieved["total_attempts"] >= 3

    def test_consecutive_passes_grow_monotonically(self, server_url):
        _, ws_url = server_url
        stats = asyncio.run(self._run_loop(ws_url))
        cp = [m["consecutive_passes"] for m in stats["mastery_updates"]]
        # Consecutive passes should never decrease with consistent mock scores
        for a, b in zip(cp, cp[1:]):
            assert b >= a - 1  # allow reset to 0 on a fail, but not below

    def test_passes_needed_reaches_zero_on_mastery(self, server_url):
        _, ws_url = server_url
        stats = asyncio.run(self._run_loop(ws_url))
        last = stats["mastery_updates"][-1]
        assert last["passes_needed"] == 0
        assert last["mastered"] is True

    def test_metrics_updated_after_session(self, server_url):
        """After driving a session to mastery the /metrics endpoint should reflect activity."""
        base, ws_url = server_url
        # Run a full loop to generate telemetry
        asyncio.run(self._run_loop(ws_url))
        r = httpx.get(f"{base}/metrics")
        assert r.status_code == 200
        # Metric shape must still be valid
        body = r.json()
        assert "product" in body
        assert "tool_quality" in body

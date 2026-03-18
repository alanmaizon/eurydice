"""
Eurydice WebSocket integration tests.

Tests the Eurydice-specific WS protocol (target.set, audio_recording,
mastery.update, mastery.achieved) using a mock Claude handler that speaks
the same protocol without calling the Anthropic API.

Run:
    cd backend && python -m pytest tests/test_ws_eurydice.py -v
"""

import asyncio
import json
import time
import uuid
import struct
import base64
import math
import pytest
from unittest.mock import patch
from starlette.testclient import TestClient

from main import app
from eurydice_session import (
    SessionState,
    EurydiceSession,
    create_session,
    drop_session,
)
from models import (
    SessionStartedMessage,
    StatusMessage,
    TextDeltaMessage,
    TextDoneMessage,
    ToolCallMessage,
    ToolResultMessage,
    LogMessage,
    StateChangedMessage,
    MasteryUpdateMessage,
    MasteryAchievedMessage,
    TargetValidationMessage,
    CaptureInvalidMessage,
)
from tools import execute_eurydice_tool_mock


# ── Mock Claude session handler ──────────────────────────────────────────────


async def _mock_claude_handler(websocket, config: dict) -> None:
    """
    Lightweight mock that replaces run_claude_session.

    Speaks the same Eurydice WS protocol:
      - session handshake
      - target.set → validation + state change
      - input.audio_recording → mock audio_analysis → mastery check
      - coaching_response → drill assigned
      - session.end
    """
    session_id = f"test-{uuid.uuid4().hex[:8]}"
    sess = create_session(session_id)

    async def send(msg):
        payload = msg.model_dump() if hasattr(msg, "model_dump") else msg
        await websocket.send_text(json.dumps(payload))

    def now():
        return "2025-01-01T00:00:00Z"

    async def emit_state(prev=None):
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
                    from presets import get_preset
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
                # Mock Claude acknowledgment
                ack = f"Target set: {description}. Record a take when ready."
                await send(TextDeltaMessage(delta=ack))
                await send(TextDoneMessage(full_text=ack))
                await send(LogMessage(event="output.done", timestamp=now()))

            elif msg_type == "input.audio_recording":
                audio_b64 = msg.get("audio_b64", "")
                duration_s = msg.get("duration_s")

                # Transition: → recording → processing_quick
                prev = sess.state
                sess.transition(SessionState.RECORDING)
                await emit_state(prev)

                prev = sess.state
                sess.force_state(SessionState.PROCESSING_QUICK)
                await emit_state(prev)

                # Run mock audio analysis
                call_id = f"call-{uuid.uuid4().hex[:8]}"
                args = {"mode": "quick", "audio_b64": audio_b64}
                if sess.target.target_bpm:
                    args["target_bpm"] = sess.target.target_bpm
                if sess.target.target_notes:
                    args["target_notes"] = sess.target.target_notes

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
                    result["_mastery"] = mastery_check.to_dict() if hasattr(mastery_check, "to_dict") else {}

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

                    # Mock coaching feedback
                    coaching_id = f"call-{uuid.uuid4().hex[:8]}"
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


# ── Helpers ──────────────────────────────────────────────────────────────────


def _recv_turn(ws, *, stop_on: str = "log", max_msgs: int = 100) -> list[dict]:
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


def _make_wav_b64(duration_s: float = 3.0, sample_rate: int = 16000) -> str:
    """Generate a minimal WAV file as base64."""
    num_samples = int(sample_rate * duration_s)
    samples = [int(32767 * math.sin(2 * math.pi * 440 * i / sample_rate)) for i in range(num_samples)]
    pcm_data = struct.pack(f"<{num_samples}h", *samples)
    data_size = len(pcm_data)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + data_size, b"WAVE",
        b"fmt ", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16,
        b"data", data_size,
    )
    return base64.b64encode(header + pcm_data).decode()


@pytest.fixture(autouse=True)
def _mock_claude():
    """Route USE_CLAUDE=True and replace run_claude_session with our mock."""
    with (
        patch("session.USE_MOCK", False),
        patch("session.USE_CLAUDE", True),
        patch("claude_client.run_claude_session", _mock_claude_handler),
    ):
        yield


@pytest.fixture
def ws():
    """Open a WS, perform handshake, yield the live socket."""
    with TestClient(app).websocket_connect("/ws") as socket:
        socket.send_json({"type": "session.start", "config": {}})
        handshake = _recv_turn(socket, stop_on="log")
        assert _find(handshake, "session.started") is not None
        yield socket


# ── Tests ────────────────────────────────────────────────────────────────────


class TestEurydiceHandshake:
    def test_handshake_includes_state(self):
        with TestClient(app).websocket_connect("/ws") as socket:
            socket.send_json({"type": "session.start", "config": {}})
            msgs = _recv_turn(socket, stop_on="log")
            state = _find(msgs, "session.state")
            assert state is not None
            assert state["state"] == "idle"


class TestTargetSet:
    def test_set_target_with_description(self, ws):
        ws.send_json({
            "type": "target.set",
            "description": "Smoke on the Water riff",
            "target_bpm": 112,
            "difficulty": "beginner",
        })
        msgs = _recv_turn(ws)

        state = _find(msgs, "session.state")
        assert state is not None
        assert state["state"] == "target_selected"

        done = _find(msgs, "output.text.done")
        assert done is not None
        assert "Smoke on the Water" in done["full_text"]

    def test_set_target_with_preset(self, ws):
        ws.send_json({
            "type": "target.set",
            "preset_id": "smoke_on_the_water",
        })
        msgs = _recv_turn(ws)

        state = _find(msgs, "session.state")
        assert state is not None
        assert state["state"] == "target_selected"

    def test_invalid_target_returns_validation_error(self, ws):
        ws.send_json({
            "type": "target.set",
            "description": "",
            "target_bpm": 90,
        })
        msgs = _recv_turn(ws, stop_on="target.validation")
        validation = _find(msgs, "target.validation")
        assert validation is not None
        assert validation["valid"] is False

    def test_unknown_preset_returns_error(self, ws):
        ws.send_json({
            "type": "target.set",
            "preset_id": "nonexistent",
        })
        msgs = _recv_turn(ws, stop_on="target.validation")
        validation = _find(msgs, "target.validation")
        assert validation is not None
        assert validation["valid"] is False


class TestAudioRecording:
    def _set_target(self, ws):
        ws.send_json({
            "type": "target.set",
            "description": "Test passage",
            "target_bpm": 120,
            "difficulty": "beginner",
        })
        _recv_turn(ws)

    def test_audio_recording_triggers_analysis(self, ws):
        self._set_target(ws)
        wav_b64 = _make_wav_b64(duration_s=3.0)
        ws.send_json({
            "type": "input.audio_recording",
            "audio_b64": wav_b64,
            "duration_s": 3.0,
        })
        msgs = _recv_turn(ws)

        tool_call = _find(msgs, "tool.call")
        assert tool_call is not None
        assert tool_call["tool_name"] == "audio_analysis"

        tool_result = _find(msgs, "tool.result")
        assert tool_result is not None

    def test_audio_recording_produces_mastery_update(self, ws):
        self._set_target(ws)
        wav_b64 = _make_wav_b64(duration_s=3.0)
        ws.send_json({
            "type": "input.audio_recording",
            "audio_b64": wav_b64,
            "duration_s": 3.0,
        })
        msgs = _recv_turn(ws)

        mastery = _find(msgs, "mastery.update")
        assert mastery is not None
        assert mastery["attempt_number"] == 1
        assert "consecutive_passes" in mastery
        assert "passes_needed" in mastery
        assert "gate_detail" in mastery

    def test_state_transitions_during_analysis(self, ws):
        self._set_target(ws)
        wav_b64 = _make_wav_b64(duration_s=3.0)
        ws.send_json({
            "type": "input.audio_recording",
            "audio_b64": wav_b64,
            "duration_s": 3.0,
        })
        msgs = _recv_turn(ws)

        states = _find_all(msgs, "session.state")
        state_values = [s["state"] for s in states]
        # Should see: recording → processing_quick → feedback_quick (or drill_assigned)
        assert "recording" in state_values
        assert "processing_quick" in state_values

    def test_coaching_response_included(self, ws):
        self._set_target(ws)
        wav_b64 = _make_wav_b64(duration_s=3.0)
        ws.send_json({
            "type": "input.audio_recording",
            "audio_b64": wav_b64,
            "duration_s": 3.0,
        })
        msgs = _recv_turn(ws)

        # Should have a coaching_response tool call
        tool_calls = _find_all(msgs, "tool.call")
        coaching_call = next(
            (t for t in tool_calls if t["tool_name"] == "coaching_response"),
            None,
        )
        assert coaching_call is not None
        assert "primary_correction" in coaching_call.get("args", {})
        assert "drill" in coaching_call.get("args", {})


class TestMasteryLoop:
    def _set_target(self, ws):
        ws.send_json({
            "type": "target.set",
            "description": "Test passage for mastery",
            "target_bpm": 120,
            "difficulty": "beginner",
        })
        _recv_turn(ws)

    def _send_take(self, ws):
        wav_b64 = _make_wav_b64(duration_s=3.0)
        ws.send_json({
            "type": "input.audio_recording",
            "audio_b64": wav_b64,
            "duration_s": 3.0,
        })
        return _recv_turn(ws)

    def test_mastery_after_three_passes(self, ws):
        self._set_target(ws)

        mastery_achieved = False
        for i in range(5):
            msgs = self._send_take(ws)
            mastery = _find(msgs, "mastery.update")
            if mastery and mastery.get("mastered"):
                mastery_achieved = True
                # Should also get mastery.achieved message
                achieved = _find(msgs, "mastery.achieved")
                assert achieved is not None
                assert achieved["total_attempts"] >= 3
                break

        assert mastery_achieved, "Expected mastery after consecutive passes"

    def test_attempt_count_increments(self, ws):
        self._set_target(ws)

        msgs1 = self._send_take(ws)
        mastery1 = _find(msgs1, "mastery.update")
        assert mastery1["attempt_number"] == 1

        msgs2 = self._send_take(ws)
        mastery2 = _find(msgs2, "mastery.update")
        assert mastery2["attempt_number"] == 2

    def test_consecutive_passes_tracked(self, ws):
        self._set_target(ws)

        msgs1 = self._send_take(ws)
        m1 = _find(msgs1, "mastery.update")

        msgs2 = self._send_take(ws)
        m2 = _find(msgs2, "mastery.update")

        # Both should pass (mock returns good scores) so consecutive should grow
        if m1["gate_detail"]["timing"]["ok"] and m1["gate_detail"]["notes"]["ok"]:
            assert m2["consecutive_passes"] >= m1["consecutive_passes"]


class TestTextInput:
    def test_text_input_during_session(self, ws):
        ws.send_json({"type": "input.text", "text": "How do I improve?"})
        msgs = _recv_turn(ws)
        done = _find(msgs, "output.text.done")
        assert done is not None
        assert "How do I improve" in done["full_text"]

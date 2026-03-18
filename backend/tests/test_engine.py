"""Tests for engine base classes: StateMachine, EvaluationGate, SessionManager, ToolRegistry."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.sessions.state_machine import StateMachine
from engine.sessions.evaluation_gate import EvaluationGate
from engine.runtime.session_manager import SessionManager
from engine.orchestration.tool_registry import ToolRegistry


# ── StateMachine ─────────────────────────────────────────────────────────────

class TestStateMachine:
    def test_valid_transition(self):
        sm = StateMachine("idle", {("idle", "running"), ("running", "done")})
        assert sm.transition("running") is True
        assert sm.state == "running"

    def test_invalid_transition_rejected(self):
        sm = StateMachine("idle", {("idle", "running")})
        assert sm.transition("done") is False
        assert sm.state == "idle"

    def test_force_state_bypasses_validation(self):
        sm = StateMachine("idle", set())
        sm.force_state("anywhere")
        assert sm.state == "anywhere"

    def test_history_recorded(self):
        sm = StateMachine("a", {("a", "b"), ("b", "c")})
        sm.transition("b")
        sm.transition("c")
        assert len(sm.history) == 2
        assert sm.history[0][0] == "a"
        assert sm.history[0][1] == "b"

    def test_invalid_transition_still_recorded_in_history(self):
        sm = StateMachine("a", set())
        sm.transition("z")
        assert len(sm.history) == 1
        assert sm.history[0][1] == "z"


# ── EvaluationGate ──────────────────────────────────────────────────────────

class TestEvaluationGate:
    def test_passing_attempt(self):
        gate = EvaluationGate({"timing": 0.8, "notes": 0.7}, consecutive_required=2)
        result = gate.record_attempt({"timing": 0.9, "notes": 0.8}, confidence=0.9)
        assert result.passed_this_attempt is True
        assert result.consecutive_passes == 1
        assert result.gate_passed is False

    def test_two_consecutive_passes_triggers_gate(self):
        gate = EvaluationGate({"timing": 0.8}, consecutive_required=2)
        gate.record_attempt({"timing": 0.9}, confidence=0.9)
        result = gate.record_attempt({"timing": 0.85}, confidence=0.8)
        assert result.gate_passed is True

    def test_failure_resets_consecutive(self):
        gate = EvaluationGate({"timing": 0.8}, consecutive_required=3)
        gate.record_attempt({"timing": 0.9}, confidence=0.9)
        gate.record_attempt({"timing": 0.9}, confidence=0.9)
        gate.record_attempt({"timing": 0.5}, confidence=0.9)  # fail
        result = gate.record_attempt({"timing": 0.9}, confidence=0.9)
        assert result.consecutive_passes == 1
        assert result.gate_passed is False

    def test_low_confidence_fails(self):
        gate = EvaluationGate({"timing": 0.5}, confidence_gate=0.7)
        result = gate.record_attempt({"timing": 0.9}, confidence=0.3)
        assert result.passed_this_attempt is False

    def test_gate_detail_includes_all_dimensions(self):
        gate = EvaluationGate({"timing": 0.8, "notes": 0.7})
        result = gate.record_attempt({"timing": 0.9, "notes": 0.6}, confidence=0.9)
        assert "timing" in result.gate_detail
        assert "notes" in result.gate_detail
        assert "confidence" in result.gate_detail
        assert result.gate_detail["notes"]["ok"] is False

    def test_to_dict(self):
        gate = EvaluationGate({"a": 0.5}, consecutive_required=3, confidence_gate=0.6)
        d = gate.to_dict()
        assert d["consecutive_required"] == 3
        assert d["confidence_gate"] == 0.6


# ── SessionManager ──────────────────────────────────────────────────────────

class TestSessionManager:
    def test_create_and_get(self):
        mgr: SessionManager[str] = SessionManager()
        mgr.create("s1", lambda sid: f"session-{sid}")
        assert mgr.get("s1") == "session-s1"

    def test_get_missing_returns_none(self):
        mgr: SessionManager[str] = SessionManager()
        assert mgr.get("nonexistent") is None

    def test_drop(self):
        mgr: SessionManager[str] = SessionManager()
        mgr.create("s1", lambda sid: sid)
        mgr.drop("s1")
        assert mgr.get("s1") is None

    def test_active_count(self):
        mgr: SessionManager[str] = SessionManager()
        mgr.create("s1", lambda sid: sid)
        mgr.create("s2", lambda sid: sid)
        assert mgr.active_count == 2


# ── ToolRegistry ────────────────────────────────────────────────────────────

class TestToolRegistry:
    def test_register_and_execute(self):
        reg = ToolRegistry()
        reg.register("add", {"name": "add"}, lambda args: args["a"] + args["b"])
        result = reg.execute("add", {"a": 1, "b": 2})
        assert result == 3

    def test_unknown_tool(self):
        reg = ToolRegistry()
        result = reg.execute("unknown", {})
        assert "error" in result

    def test_mock_execution(self):
        reg = ToolRegistry()
        reg.register(
            "fetch",
            {"name": "fetch"},
            lambda args: "live",
            mock_executor=lambda args: "mock",
        )
        assert reg.execute("fetch", {}, use_mock=True) == "mock"
        assert reg.execute("fetch", {}, use_mock=False) == "live"

    def test_get_declarations(self):
        reg = ToolRegistry()
        reg.register("t1", {"name": "t1", "desc": "tool 1"}, lambda a: None)
        reg.register("t2", {"name": "t2", "desc": "tool 2"}, lambda a: None)
        decls = reg.get_declarations()
        assert len(decls) == 2
        assert decls[0]["name"] == "t1"

    def test_has_tool(self):
        reg = ToolRegistry()
        reg.register("x", {}, lambda a: None)
        assert reg.has_tool("x") is True
        assert reg.has_tool("y") is False

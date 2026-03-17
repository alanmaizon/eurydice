"""
Eurydice session state machine and mastery gate.

SessionState models the full lifecycle of a guitar practice session.
MasteryGate tracks consecutive passes against defined thresholds.
EurydiceSession holds both, plus the target passage definition.

All state is in-memory keyed by session_id. Sessions are created at
websocket open and dropped at close — no persistence layer yet.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── State machine ─────────────────────────────────────────────────────────────

class SessionState(str, Enum):
    """Ordered lifecycle states for a Eurydice practice session."""
    IDLE               = "idle"               # session open, no target set
    TARGET_SELECTED    = "target_selected"    # target passage + BPM defined
    RECORDING          = "recording"          # user recording in progress
    PROCESSING_QUICK   = "processing_quick"   # quick analysis running
    FEEDBACK_QUICK     = "feedback_quick"     # quick feedback delivered
    PROCESSING_DEEP    = "processing_deep"    # deep analysis running
    FEEDBACK_DEEP      = "feedback_deep"      # deep feedback delivered
    DRILL_ASSIGNED     = "drill_assigned"     # drill prescribed, awaiting retry
    RETRY_REQUESTED    = "retry_requested"    # user signalled retry
    CAPTURE_INVALID    = "capture_invalid"    # analysis confidence < threshold
    MASTERED           = "mastered"           # mastery gate passed
    ERROR              = "error"


# Valid transitions: (from_state, to_state)
_VALID_TRANSITIONS: set[tuple[SessionState, SessionState]] = {
    (SessionState.IDLE,             SessionState.TARGET_SELECTED),
    (SessionState.TARGET_SELECTED,  SessionState.RECORDING),
    (SessionState.TARGET_SELECTED,  SessionState.PROCESSING_QUICK),  # direct from text/audio
    (SessionState.RECORDING,        SessionState.PROCESSING_QUICK),
    (SessionState.PROCESSING_QUICK, SessionState.FEEDBACK_QUICK),
    (SessionState.PROCESSING_QUICK, SessionState.CAPTURE_INVALID),
    (SessionState.FEEDBACK_QUICK,   SessionState.PROCESSING_DEEP),
    (SessionState.FEEDBACK_QUICK,   SessionState.DRILL_ASSIGNED),
    (SessionState.FEEDBACK_QUICK,   SessionState.RETRY_REQUESTED),
    (SessionState.PROCESSING_DEEP,  SessionState.FEEDBACK_DEEP),
    (SessionState.PROCESSING_DEEP,  SessionState.CAPTURE_INVALID),
    (SessionState.FEEDBACK_DEEP,    SessionState.DRILL_ASSIGNED),
    (SessionState.FEEDBACK_DEEP,    SessionState.RETRY_REQUESTED),
    (SessionState.DRILL_ASSIGNED,   SessionState.RETRY_REQUESTED),
    (SessionState.RETRY_REQUESTED,  SessionState.RECORDING),
    (SessionState.RETRY_REQUESTED,  SessionState.PROCESSING_QUICK),
    (SessionState.CAPTURE_INVALID,  SessionState.RECORDING),
    (SessionState.CAPTURE_INVALID,  SessionState.TARGET_SELECTED),
    # Any state → mastered (gate can trigger after deep or quick)
    (SessionState.FEEDBACK_QUICK,   SessionState.MASTERED),
    (SessionState.FEEDBACK_DEEP,    SessionState.MASTERED),
    # Any state → error
    *{(s, SessionState.ERROR) for s in SessionState},
}


# ── Attempt record ─────────────────────────────────────────────────────────────

@dataclass
class AttemptRecord:
    attempt_number: int
    timing_score: float
    notes_score: float
    overall_score: float
    analysis_confidence: float  # min(tempo_confidence, pitch_confidence)
    passed: bool
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_number": self.attempt_number,
            "timing_score": self.timing_score,
            "notes_score": self.notes_score,
            "overall_score": self.overall_score,
            "analysis_confidence": self.analysis_confidence,
            "passed": self.passed,
            "timestamp": self.timestamp,
        }


# ── Mastery gate ───────────────────────────────────────────────────────────────

CONSECUTIVE_PASSES_REQUIRED = 3
CONFIDENCE_GATE = 0.70


@dataclass
class MasteryGate:
    """
    Tracks attempt history and determines when mastery is achieved.

    Mastery requires CONSECUTIVE_PASSES_REQUIRED consecutive attempts
    all meeting timing_threshold, notes_threshold, and confidence_gate.
    """
    timing_threshold: float = 0.85
    notes_threshold: float = 0.80
    consecutive_passes_required: int = CONSECUTIVE_PASSES_REQUIRED
    confidence_gate: float = CONFIDENCE_GATE

    attempts: list[AttemptRecord] = field(default_factory=list)
    consecutive_passes: int = 0
    mastered: bool = False

    def record_attempt(self, analysis_result: dict[str, Any]) -> "MasteryCheckResult":
        """
        Ingest a scored analysis result and update mastery state.
        Returns a MasteryCheckResult describing the outcome.
        """
        scores = analysis_result.get("performance_scores", {})
        timing = float(scores.get("timing", 0.0))
        notes = float(scores.get("notes", 0.0))
        overall = float(scores.get("overall", 0.0))

        # Confidence = min of tempo and pitch confidence (most conservative)
        confidence = min(
            float(analysis_result.get("tempo_confidence", 0.0)),
            float(analysis_result.get("pitch_confidence", scores.get("notes", 0.0))),
        )

        # A pass requires all three gates
        passed = (
            confidence >= self.confidence_gate
            and timing >= self.timing_threshold
            and notes >= self.notes_threshold
        )

        attempt = AttemptRecord(
            attempt_number=len(self.attempts) + 1,
            timing_score=timing,
            notes_score=notes,
            overall_score=overall,
            analysis_confidence=confidence,
            passed=passed,
        )
        self.attempts.append(attempt)

        if passed:
            self.consecutive_passes += 1
        else:
            self.consecutive_passes = 0

        if self.consecutive_passes >= self.consecutive_passes_required:
            self.mastered = True

        return MasteryCheckResult(
            passed_this_attempt=passed,
            consecutive_passes=self.consecutive_passes,
            passes_needed=max(0, self.consecutive_passes_required - self.consecutive_passes),
            mastered=self.mastered,
            attempt=attempt,
            gate_detail={
                "timing": {"score": timing, "threshold": self.timing_threshold, "ok": timing >= self.timing_threshold},
                "notes":  {"score": notes,  "threshold": self.notes_threshold,  "ok": notes  >= self.notes_threshold},
                "confidence": {"score": confidence, "threshold": self.confidence_gate, "ok": confidence >= self.confidence_gate},
            },
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "consecutive_passes": self.consecutive_passes,
            "passes_needed": max(0, self.consecutive_passes_required - self.consecutive_passes),
            "mastered": self.mastered,
            "total_attempts": len(self.attempts),
            "thresholds": {
                "timing": self.timing_threshold,
                "notes": self.notes_threshold,
                "confidence": self.confidence_gate,
                "consecutive_required": self.consecutive_passes_required,
            },
            "attempts": [a.to_dict() for a in self.attempts[-5:]],  # last 5 only
        }


@dataclass
class MasteryCheckResult:
    passed_this_attempt: bool
    consecutive_passes: int
    passes_needed: int
    mastered: bool
    attempt: AttemptRecord
    gate_detail: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed_this_attempt": self.passed_this_attempt,
            "consecutive_passes": self.consecutive_passes,
            "passes_needed": self.passes_needed,
            "mastered": self.mastered,
            "gate_detail": self.gate_detail,
        }


# ── Target passage ─────────────────────────────────────────────────────────────

@dataclass
class TargetPassage:
    """What the user is trying to master."""
    description: str = ""          # human description, e.g. "opening lick of Comfortably Numb"
    target_bpm: float | None = None
    target_notes: list[dict[str, Any]] = field(default_factory=list)  # [{onset_s, midi}, ...]
    difficulty: str = "beginner"   # beginner / intermediate / advanced

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "target_bpm": self.target_bpm,
            "target_notes_count": len(self.target_notes),
            "difficulty": self.difficulty,
        }


# ── Session ────────────────────────────────────────────────────────────────────

class EurydiceSession:
    """
    Holds all mutable state for one Eurydice WebSocket session.
    Thread-safety note: each WS session runs in a single asyncio task — no locks needed.
    """

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.state = SessionState.IDLE
        self.target: TargetPassage = TargetPassage()
        self.mastery_gate = MasteryGate()
        self.created_at = time.time()
        self._history: list[tuple[SessionState, SessionState, float]] = []

    # ── State transitions ──────────────────────────────────────────────────────

    def transition(self, to: SessionState) -> bool:
        """
        Attempt a state transition. Returns True if allowed, False if not.
        Logs the transition regardless.
        """
        allowed = (self.state, to) in _VALID_TRANSITIONS
        self._history.append((self.state, to, time.time()))
        if allowed:
            self.state = to
        return allowed

    def force_state(self, to: SessionState) -> None:
        """Set state unconditionally (e.g. on error)."""
        self._history.append((self.state, to, time.time()))
        self.state = to

    # ── Target ────────────────────────────────────────────────────────────────

    def set_target(
        self,
        description: str = "",
        target_bpm: float | None = None,
        target_notes: list[dict[str, Any]] | None = None,
        difficulty: str = "beginner",
    ) -> None:
        self.target = TargetPassage(
            description=description,
            target_bpm=target_bpm,
            target_notes=target_notes or [],
            difficulty=difficulty,
        )
        # Adjust mastery thresholds by difficulty
        if difficulty == "beginner":
            self.mastery_gate.timing_threshold = 0.75
            self.mastery_gate.notes_threshold   = 0.70
        elif difficulty == "intermediate":
            self.mastery_gate.timing_threshold = 0.85
            self.mastery_gate.notes_threshold   = 0.80
        elif difficulty == "advanced":
            self.mastery_gate.timing_threshold = 0.92
            self.mastery_gate.notes_threshold   = 0.90
        self.transition(SessionState.TARGET_SELECTED)

    # ── Mastery check ──────────────────────────────────────────────────────────

    def record_attempt(self, analysis_result: dict[str, Any]) -> MasteryCheckResult:
        """
        Process a scored audio analysis result.
        Advances state to MASTERED if the gate passes, otherwise to FEEDBACK_QUICK/DEEP.
        """
        check = self.mastery_gate.record_attempt(analysis_result)
        if check.mastered:
            self.force_state(SessionState.MASTERED)
        return check

    # ── Serialisation ──────────────────────────────────────────────────────────

    def to_context_dict(self) -> dict[str, Any]:
        """
        Compact summary injected into Claude's system prompt so it always
        knows current session state without needing a separate tool call.
        """
        return {
            "state": self.state.value,
            "target": self.target.to_dict(),
            "mastery": self.mastery_gate.to_dict(),
        }


# ── In-memory session store ────────────────────────────────────────────────────

_sessions: dict[str, EurydiceSession] = {}


def create_session(session_id: str) -> EurydiceSession:
    sess = EurydiceSession(session_id)
    _sessions[session_id] = sess
    return sess


def get_session(session_id: str) -> EurydiceSession | None:
    return _sessions.get(session_id)


def drop_session(session_id: str) -> None:
    _sessions.pop(session_id, None)

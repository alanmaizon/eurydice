"""
In-memory telemetry collector for Eurydice session and tool events.

Records structured events and computes metrics required by CLAUDE.md:
- Product: weekly_mastery_events_per_active_user
- Session: attempt_count, time_to_first_feedback, time_to_mastery, retry_rate, capture_failure_rate
- Tool quality: avg scores, false_mastery_rate, low_confidence_block_rate
- Trust: user_disagreement_reports (placeholder)

Production will swap this for a persistent backend. Events are stored in memory
with FIFO eviction at MAX_EVENTS to prevent unbounded growth.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


MAX_EVENTS = 10_000


@dataclass
class TelemetryEvent:
    event_type: str       # e.g. "attempt", "mastery", "capture_failure", "session.start"
    session_id: str
    timestamp: float
    data: dict[str, Any] = field(default_factory=dict)


class TelemetryCollector:
    """In-memory event store with metric computation."""

    def __init__(self) -> None:
        self._events: list[TelemetryEvent] = []
        self._lock = asyncio.Lock()

    async def record(self, event_type: str, session_id: str, data: dict[str, Any] | None = None) -> None:
        async with self._lock:
            self._events.append(TelemetryEvent(
                event_type=event_type,
                session_id=session_id,
                timestamp=time.time(),
                data=data or {},
            ))
            # FIFO eviction
            if len(self._events) > MAX_EVENTS:
                self._events = self._events[-MAX_EVENTS:]

    def _events_for(self, session_id: str) -> list[TelemetryEvent]:
        return [e for e in self._events if e.session_id == session_id]

    def _events_of_type(self, event_type: str) -> list[TelemetryEvent]:
        return [e for e in self._events if e.event_type == event_type]

    def compute_session_metrics(self, session_id: str) -> dict[str, Any]:
        """Compute per-session metrics from recorded events."""
        events = self._events_for(session_id)
        attempts = [e for e in events if e.event_type == "attempt"]
        captures_failed = [e for e in events if e.event_type == "capture_failure"]
        masteries = [e for e in events if e.event_type == "mastery"]
        feedbacks = [e for e in events if e.event_type == "feedback_delivered"]
        session_starts = [e for e in events if e.event_type == "session.start"]

        attempt_count = len(attempts)
        capture_failure_count = len(captures_failed)
        total_recordings = attempt_count + capture_failure_count

        # Time to first feedback
        time_to_first_feedback_ms: float | None = None
        if feedbacks and session_starts:
            time_to_first_feedback_ms = round(
                (feedbacks[0].timestamp - session_starts[0].timestamp) * 1000, 1
            )

        # Time to mastery
        time_to_mastery_s: float | None = None
        if masteries and session_starts:
            time_to_mastery_s = round(
                masteries[0].timestamp - session_starts[0].timestamp, 1
            )

        # Retry rate: attempts beyond the first / total attempts
        retry_rate = round((attempt_count - 1) / attempt_count, 2) if attempt_count > 1 else 0.0

        # Capture failure rate
        capture_failure_rate = round(
            capture_failure_count / total_recordings, 2
        ) if total_recordings > 0 else 0.0

        return {
            "session_id": session_id,
            "attempt_count": attempt_count,
            "time_to_first_feedback_ms": time_to_first_feedback_ms,
            "time_to_mastery_s": time_to_mastery_s,
            "retry_rate": retry_rate,
            "capture_failure_rate": capture_failure_rate,
        }

    def compute_product_metrics(self) -> dict[str, Any]:
        """Compute aggregate product metrics across all sessions."""
        mastery_events = self._events_of_type("mastery")
        session_starts = self._events_of_type("session.start")

        # Unique active sessions (any session with at least one event)
        active_sessions = set(e.session_id for e in self._events)
        active_count = len(active_sessions)

        # Weekly mastery events per active user (simplified: all time, not windowed)
        total_mastery = len(mastery_events)
        wme_per_au = round(total_mastery / active_count, 2) if active_count > 0 else 0.0

        return {
            "total_sessions": len(session_starts),
            "active_sessions": active_count,
            "total_mastery_events": total_mastery,
            "weekly_mastery_events_per_active_user": wme_per_au,
        }

    def compute_tool_quality_metrics(self) -> dict[str, Any]:
        """Aggregate tool quality metrics from attempt events."""
        attempts = self._events_of_type("attempt")
        captures_failed = self._events_of_type("capture_failure")

        if not attempts:
            return {
                "total_attempts": 0,
                "avg_timing_score": None,
                "avg_note_score": None,
                "avg_analysis_confidence": None,
                "false_mastery_rate": 0.0,
                "low_confidence_block_rate": 0.0,
            }

        timing_scores = [e.data.get("timing_score", 0) for e in attempts]
        note_scores = [e.data.get("notes_score", 0) for e in attempts]
        confidences = [e.data.get("analysis_confidence", 0) for e in attempts]

        total_recordings = len(attempts) + len(captures_failed)

        return {
            "total_attempts": len(attempts),
            "avg_timing_score": round(sum(timing_scores) / len(timing_scores), 3),
            "avg_note_score": round(sum(note_scores) / len(note_scores), 3),
            "avg_analysis_confidence": round(sum(confidences) / len(confidences), 3),
            "false_mastery_rate": 0.0,  # requires ground truth, placeholder
            "low_confidence_block_rate": round(
                len(captures_failed) / total_recordings, 3
            ) if total_recordings > 0 else 0.0,
        }

    @property
    def events(self) -> list[TelemetryEvent]:
        """Read-only access to events for testing."""
        return list(self._events)


# Singleton
_collector = TelemetryCollector()


def get_collector() -> TelemetryCollector:
    return _collector

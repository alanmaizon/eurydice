"""Tests for the telemetry collector."""

import asyncio
import pytest
from telemetry import TelemetryCollector


@pytest.fixture
def collector():
    return TelemetryCollector()


def run(coro):
    """Helper to run async functions in tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


class TestTelemetryCollector:
    def test_record_stores_events(self, collector):
        run(collector.record("session.start", "s1", {"foo": "bar"}))
        assert len(collector.events) == 1
        assert collector.events[0].event_type == "session.start"
        assert collector.events[0].session_id == "s1"

    def test_fifo_eviction(self, collector):
        for i in range(15000):
            run(collector.record("attempt", f"s{i % 10}", {"i": i}))
        assert len(collector.events) == 10000  # MAX_EVENTS

    def test_session_metrics_attempt_count(self, collector):
        run(collector.record("session.start", "s1"))
        run(collector.record("attempt", "s1", {"timing_score": 0.8}))
        run(collector.record("attempt", "s1", {"timing_score": 0.9}))
        metrics = collector.compute_session_metrics("s1")
        assert metrics["attempt_count"] == 2
        assert metrics["retry_rate"] == 0.5

    def test_session_metrics_capture_failure_rate(self, collector):
        run(collector.record("session.start", "s1"))
        run(collector.record("attempt", "s1"))
        run(collector.record("capture_failure", "s1"))
        run(collector.record("capture_failure", "s1"))
        metrics = collector.compute_session_metrics("s1")
        assert metrics["capture_failure_rate"] == pytest.approx(0.67, abs=0.01)

    def test_product_metrics(self, collector):
        run(collector.record("session.start", "s1"))
        run(collector.record("session.start", "s2"))
        run(collector.record("mastery", "s1"))
        run(collector.record("mastery", "s2"))
        run(collector.record("mastery", "s2"))
        metrics = collector.compute_product_metrics()
        assert metrics["total_mastery_events"] == 3
        assert metrics["active_sessions"] == 2
        assert metrics["weekly_mastery_events_per_active_user"] == 1.5

    def test_tool_quality_metrics(self, collector):
        run(collector.record("attempt", "s1", {
            "timing_score": 0.8, "notes_score": 0.7, "analysis_confidence": 0.9,
        }))
        run(collector.record("attempt", "s1", {
            "timing_score": 0.9, "notes_score": 0.8, "analysis_confidence": 0.85,
        }))
        run(collector.record("capture_failure", "s1"))
        metrics = collector.compute_tool_quality_metrics()
        assert metrics["total_attempts"] == 2
        assert metrics["avg_timing_score"] == 0.85
        assert metrics["low_confidence_block_rate"] == pytest.approx(0.333, abs=0.01)

    def test_empty_metrics(self, collector):
        metrics = collector.compute_tool_quality_metrics()
        assert metrics["total_attempts"] == 0
        assert metrics["avg_timing_score"] is None

    def test_time_to_first_feedback(self, collector):
        import time
        run(collector.record("session.start", "s1"))
        time.sleep(0.01)
        run(collector.record("feedback_delivered", "s1"))
        metrics = collector.compute_session_metrics("s1")
        assert metrics["time_to_first_feedback_ms"] is not None
        assert metrics["time_to_first_feedback_ms"] > 0

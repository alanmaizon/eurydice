"""Tests for EurydiceSession: target validation, state transitions, mastery gate."""

import pytest
from eurydice_session import (
    EurydiceSession,
    SessionState,
    MasteryGate,
    TargetValidationResult,
)


class TestTargetValidation:
    def test_valid_target_transitions_to_target_selected(self):
        sess = EurydiceSession("test-1")
        result = sess.set_target(description="Smoke on the Water riff", target_bpm=112)
        assert result.valid is True
        assert sess.state == SessionState.TARGET_SELECTED

    def test_empty_description_rejected(self):
        sess = EurydiceSession("test-2")
        result = sess.set_target(description="", target_bpm=90)
        assert result.valid is False
        assert "Description must be at least 3 characters" in result.errors
        assert sess.state == SessionState.IDLE

    def test_short_description_rejected(self):
        sess = EurydiceSession("test-3")
        result = sess.set_target(description="ab")
        assert result.valid is False
        assert sess.state == SessionState.IDLE

    def test_bpm_too_low_rejected(self):
        sess = EurydiceSession("test-4")
        result = sess.set_target(description="Test passage", target_bpm=10)
        assert result.valid is False
        assert any("BPM" in e for e in result.errors)

    def test_bpm_too_high_rejected(self):
        sess = EurydiceSession("test-5")
        result = sess.set_target(description="Test passage", target_bpm=500)
        assert result.valid is False

    def test_bpm_none_is_valid(self):
        sess = EurydiceSession("test-6")
        result = sess.set_target(description="Test passage", target_bpm=None)
        assert result.valid is True

    def test_invalid_notes_stripped_with_warning(self):
        sess = EurydiceSession("test-7")
        notes = [
            {"onset_s": 0.0, "midi": 60},       # valid
            {"onset_s": -1.0, "midi": 60},       # invalid onset
            {"onset_s": 0.5, "midi": 200},       # invalid MIDI
            {"onset_s": 1.0, "midi": 48},        # valid
        ]
        result = sess.set_target(description="Test passage", target_notes=notes)
        assert result.valid is True
        assert "Stripped 2 invalid note(s)" in result.warnings[0]
        assert len(sess.target.target_notes) == 2

    def test_unknown_difficulty_defaults_with_warning(self):
        sess = EurydiceSession("test-8")
        result = sess.set_target(description="Test passage", difficulty="expert")
        assert result.valid is True
        assert any("Unknown difficulty" in w for w in result.warnings)
        assert sess.target.difficulty == "beginner"

    def test_difficulty_adjusts_thresholds(self):
        sess = EurydiceSession("test-9")
        sess.set_target(description="Test", difficulty="advanced")
        assert sess.mastery_gate.timing_threshold == 0.92
        assert sess.mastery_gate.notes_threshold == 0.90

    def test_target_set_at_timestamp(self):
        sess = EurydiceSession("test-10")
        assert sess.target_set_at is None
        sess.set_target(description="Test passage")
        assert sess.target_set_at is not None


class TestStateTransitions:
    def test_valid_transition(self):
        sess = EurydiceSession("test-t1")
        sess.set_target(description="Test passage")
        assert sess.transition(SessionState.RECORDING) is True
        assert sess.state == SessionState.RECORDING

    def test_invalid_transition(self):
        sess = EurydiceSession("test-t2")
        # IDLE -> RECORDING is not valid
        assert sess.transition(SessionState.RECORDING) is False
        assert sess.state == SessionState.IDLE

    def test_capture_invalid_to_recording(self):
        sess = EurydiceSession("test-t3")
        sess.force_state(SessionState.CAPTURE_INVALID)
        assert sess.transition(SessionState.RECORDING) is True

    def test_any_state_to_error(self):
        for state in SessionState:
            sess = EurydiceSession(f"test-err-{state.value}")
            sess.force_state(state)
            assert sess.transition(SessionState.ERROR) is True


class TestMasteryGate:
    def _make_result(self, timing=0.9, notes=0.85, confidence=0.8):
        return {
            "analysis_confidence": confidence,
            "tempo_confidence": confidence,
            "pitch_confidence": confidence,
            "performance_scores": {
                "timing": timing,
                "notes": notes,
                "overall": (timing + notes) / 2,
            },
        }

    def test_passing_attempt(self):
        gate = MasteryGate()
        result = gate.record_attempt(self._make_result())
        assert result.passed_this_attempt is True
        assert result.consecutive_passes == 1

    def test_low_confidence_does_not_pass(self):
        gate = MasteryGate()
        result = gate.record_attempt(self._make_result(confidence=0.5))
        assert result.passed_this_attempt is False
        assert result.consecutive_passes == 0

    def test_three_consecutive_passes_mastery(self):
        gate = MasteryGate()
        for _ in range(3):
            result = gate.record_attempt(self._make_result())
        assert result.mastered is True

    def test_failure_resets_consecutive(self):
        gate = MasteryGate()
        gate.record_attempt(self._make_result())
        gate.record_attempt(self._make_result())
        gate.record_attempt(self._make_result(timing=0.3))  # fail
        result = gate.record_attempt(self._make_result())
        assert result.consecutive_passes == 1
        assert result.mastered is False

    def test_reads_analysis_confidence_from_result(self):
        gate = MasteryGate()
        result_data = {
            "analysis_confidence": 0.9,
            "tempo_confidence": 0.5,  # would be low without analysis_confidence
            "pitch_confidence": 0.5,
            "performance_scores": {"timing": 0.9, "notes": 0.9, "overall": 0.9},
        }
        check = gate.record_attempt(result_data)
        assert check.attempt.analysis_confidence == 0.9
        assert check.passed_this_attempt is True

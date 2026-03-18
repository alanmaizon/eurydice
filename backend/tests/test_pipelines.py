"""
Tests for Eurydice audio and vision pipelines.

Tests helper functions directly and verifies graceful degradation
when ML libraries are missing or input is invalid.
"""

import base64
import struct
import pytest
from typing import Any
from unittest.mock import patch


# ── Audio pipeline tests ─────────────────────────────────────────────────────


def _make_wav_b64(duration_s: float = 3.0, sample_rate: int = 16000, freq: float = 440.0) -> str:
    """Generate a minimal WAV file (sine wave) as base64."""
    import math
    num_samples = int(sample_rate * duration_s)
    samples = [int(32767 * math.sin(2 * math.pi * freq * i / sample_rate)) for i in range(num_samples)]
    pcm_data = struct.pack(f"<{num_samples}h", *samples)

    # WAV header
    data_size = len(pcm_data)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + data_size, b"WAVE",
        b"fmt ", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16,
        b"data", data_size,
    )
    return base64.b64encode(header + pcm_data).decode()


class TestAudioPipelineNoAudio:
    """Test audio pipeline with missing/invalid input."""

    def test_no_audio_returns_error(self):
        from domains.eurydice.pipelines.audio.pipeline import analyze_audio
        result = analyze_audio({"mode": "quick"})
        assert "error" in result
        assert result["mode"] == "quick"

    def test_empty_b64_returns_error(self):
        from domains.eurydice.pipelines.audio.pipeline import analyze_audio
        result = analyze_audio({"mode": "quick", "audio_b64": ""})
        assert "error" in result

    def test_invalid_b64_returns_error(self):
        from domains.eurydice.pipelines.audio.pipeline import analyze_audio
        result = analyze_audio({"mode": "quick", "audio_b64": "not-valid-base64!!!"})
        assert "error" in result or "warnings" in result


class TestAudioPipelineWithLibrosa:
    """Test audio pipeline with real librosa (if available)."""

    @pytest.fixture(autouse=True)
    def _skip_if_no_librosa(self):
        try:
            import librosa  # noqa: F401
        except ImportError:
            pytest.skip("librosa not installed")

    def test_quick_mode_returns_scores(self):
        from domains.eurydice.pipelines.audio.pipeline import analyze_audio
        wav_b64 = _make_wav_b64(duration_s=3.0)
        result = analyze_audio({"mode": "quick", "audio_b64": wav_b64})
        assert result["mode"] == "quick"
        assert "performance_scores" in result
        assert "timing" in result["performance_scores"]
        assert "notes" in result["performance_scores"]
        assert "overall" in result["performance_scores"]
        assert "analysis_confidence" in result
        assert isinstance(result["analysis_confidence"], float)

    def test_quick_mode_has_tempo(self):
        from domains.eurydice.pipelines.audio.pipeline import analyze_audio
        wav_b64 = _make_wav_b64(duration_s=3.0)
        result = analyze_audio({"mode": "quick", "audio_b64": wav_b64})
        assert "tempo_bpm" in result
        assert "tempo_confidence" in result
        assert isinstance(result["tempo_bpm"], float)

    def test_quick_mode_has_capture_quality(self):
        from domains.eurydice.pipelines.audio.pipeline import analyze_audio
        wav_b64 = _make_wav_b64(duration_s=3.0)
        result = analyze_audio({"mode": "quick", "audio_b64": wav_b64})
        assert "capture_quality" in result
        cq = result["capture_quality"]
        assert "duration_ok" in cq
        assert "noise_floor_ok" in cq
        assert "clipping_detected" in cq
        assert "overall" in cq

    def test_short_recording_warns(self):
        from domains.eurydice.pipelines.audio.pipeline import analyze_audio
        wav_b64 = _make_wav_b64(duration_s=1.0)
        result = analyze_audio({"mode": "quick", "audio_b64": wav_b64})
        # Short recording should either fail quality check or produce a warning
        has_warning = any("short" in w.lower() for w in result.get("warnings", []))
        poor_quality = result.get("capture_quality", {}).get("overall") == "poor"
        assert has_warning or poor_quality

    def test_deep_mode_without_basic_pitch(self):
        from domains.eurydice.pipelines.audio.pipeline import analyze_audio
        wav_b64 = _make_wav_b64(duration_s=3.0)
        result = analyze_audio({"mode": "deep", "audio_b64": wav_b64})
        assert result["mode"] == "deep"
        # Should still have base scores even if basic-pitch isn't installed
        assert "performance_scores" in result

    def test_analysis_ms_tracked(self):
        from domains.eurydice.pipelines.audio.pipeline import analyze_audio
        wav_b64 = _make_wav_b64(duration_s=3.0)
        result = analyze_audio({"mode": "quick", "audio_b64": wav_b64})
        assert "_analysis_ms" in result
        assert result["_analysis_ms"] > 0


class TestAudioHelpers:
    """Test internal helper functions."""

    @pytest.fixture(autouse=True)
    def _skip_if_no_librosa(self):
        try:
            import numpy  # noqa: F401
        except ImportError:
            pytest.skip("numpy not installed")

    def test_capture_quality_good(self):
        import numpy as np
        from domains.eurydice.pipelines.audio.pipeline import _capture_quality
        # 3 seconds of normal audio
        y = np.sin(2 * np.pi * 440 * np.arange(48000) / 16000).astype(np.float32)
        cq = _capture_quality(y, 16000, 3.0)
        assert cq["duration_ok"] is True
        assert cq["noise_floor_ok"] is True
        assert cq["overall"] in ("good", "marginal")

    def test_capture_quality_too_short(self):
        import numpy as np
        from domains.eurydice.pipelines.audio.pipeline import _capture_quality
        y = np.sin(2 * np.pi * 440 * np.arange(8000) / 16000).astype(np.float32)
        cq = _capture_quality(y, 16000, 0.5)
        assert cq["duration_ok"] is False
        assert cq["overall"] == "poor"

    def test_capture_quality_silent(self):
        import numpy as np
        from domains.eurydice.pipelines.audio.pipeline import _capture_quality
        y = np.zeros(48000, dtype=np.float32)
        cq = _capture_quality(y, 16000, 3.0)
        assert cq["noise_floor_ok"] is False
        assert cq["overall"] == "poor"

    def test_timing_score_with_data(self):
        from domains.eurydice.pipelines.audio.pipeline import _timing_score
        # Perfect alignment: onsets exactly on beats
        onsets = [0.0, 0.5, 1.0, 1.5]
        beats = [0.0, 0.5, 1.0, 1.5]
        score = _timing_score(onsets, beats, 120.0)
        assert score >= 0.9  # near-perfect

    def test_timing_score_empty(self):
        from domains.eurydice.pipelines.audio.pipeline import _timing_score
        assert _timing_score([], [], 120.0) == 0.5  # default fallback

    def test_alignment_metrics(self):
        from domains.eurydice.pipelines.audio.pipeline import _alignment_metrics
        detected = [
            {"onset_s": 0.0, "midi": 60},
            {"onset_s": 0.5, "midi": 62},
            {"onset_s": 1.0, "midi": 64},
        ]
        target = [
            {"onset_s": 0.0, "midi": 60},
            {"onset_s": 0.5, "midi": 62},
            {"onset_s": 1.0, "midi": 64},
        ]
        metrics = _alignment_metrics(detected, target)
        assert metrics["note_f1"] == 1.0  # perfect match
        assert metrics["precision"] == 1.0
        assert metrics["recall"] == 1.0

    def test_alignment_metrics_partial_match(self):
        from domains.eurydice.pipelines.audio.pipeline import _alignment_metrics
        detected = [
            {"onset_s": 0.0, "midi": 60},
            {"onset_s": 0.5, "midi": 63},  # wrong note
        ]
        target = [
            {"onset_s": 0.0, "midi": 60},
            {"onset_s": 0.5, "midi": 62},
        ]
        metrics = _alignment_metrics(detected, target)
        assert metrics["note_f1"] < 1.0
        assert metrics["recall"] == 0.5


# ── Vision pipeline tests ────────────────────────────────────────────────────


class TestVisionPipelineNoImage:
    """Test vision pipeline with missing/invalid input."""

    def test_no_image_returns_error(self):
        from domains.eurydice.pipelines.vision.hands import analyze_vision
        result = analyze_vision({})
        assert "error" in result or result.get("hands_detected") == 0

    def test_empty_b64_returns_error(self):
        from domains.eurydice.pipelines.vision.hands import analyze_vision
        result = analyze_vision({"image_b64": ""})
        assert "error" in result or result.get("hands_detected") == 0

    def test_invalid_b64_returns_error(self):
        from domains.eurydice.pipelines.vision.hands import analyze_vision
        result = analyze_vision({"image_b64": "not-valid-base64!!!"})
        assert "error" in result or "capture_warnings" in result


class TestVisionDetectFlags:
    """Test technique flag detection with synthetic landmarks."""

    @pytest.fixture(autouse=True)
    def _skip_if_no_numpy(self):
        try:
            import numpy  # noqa: F401
        except ImportError:
            pytest.skip("numpy not installed")

    def _make_neutral_landmarks(self) -> list[tuple[float, float, float]]:
        """Generate 21 neutral hand landmarks (no flags should trigger)."""
        return [(0.5, 0.5, 0.0)] * 21

    def test_collapsed_wrist_detected(self):
        from domains.eurydice.pipelines.vision.hands import _detect_flags
        lm = self._make_neutral_landmarks()
        # Place wrist far below knuckles (high y = lower on screen)
        lm[0] = (0.5, 0.8, 0.0)   # wrist
        lm[5] = (0.5, 0.5, 0.0)   # index MCP
        lm[9] = (0.5, 0.5, 0.0)   # middle MCP
        lm[13] = (0.5, 0.5, 0.0)  # ring MCP
        lm[17] = (0.5, 0.5, 0.0)  # pinky MCP
        flags = _detect_flags(lm, "left", "fretting_hand")
        flag_names = [f["flag"] for f in flags]
        assert "collapsed_wrist" in flag_names

    def test_thumb_over_neck_detected(self):
        from domains.eurydice.pipelines.vision.hands import _detect_flags
        lm = self._make_neutral_landmarks()
        # Place thumb tip very close to index tip (x-gap < 0.08)
        lm[4] = (0.50, 0.5, 0.0)  # thumb tip
        lm[8] = (0.52, 0.5, 0.0)  # index tip
        flags = _detect_flags(lm, "left", "fretting_hand")
        flag_names = [f["flag"] for f in flags]
        assert "thumb_over_neck" in flag_names

    def test_no_flags_for_right_hand_on_fretting_focus(self):
        from domains.eurydice.pipelines.vision.hands import _detect_flags
        lm = self._make_neutral_landmarks()
        # Even with bad landmarks, fretting_hand focus shouldn't flag right hand
        lm[0] = (0.5, 0.9, 0.0)  # wrist very low
        flags = _detect_flags(lm, "right", "fretting_hand")
        assert len(flags) == 0

    def test_flag_confidence_bounded(self):
        from domains.eurydice.pipelines.vision.hands import _detect_flags
        lm = self._make_neutral_landmarks()
        lm[0] = (0.5, 1.0, 0.0)   # extreme wrist drop
        lm[5] = (0.5, 0.3, 0.0)
        lm[9] = (0.5, 0.3, 0.0)
        lm[13] = (0.5, 0.3, 0.0)
        lm[17] = (0.5, 0.3, 0.0)
        flags = _detect_flags(lm, "left", "both")
        for f in flags:
            assert 0.0 <= f["confidence"] <= 1.0


# ── Tool executor tests ──────────────────────────────────────────────────────


class TestToolExecutors:
    """Test tool executors in tools.py."""

    def test_mock_audio_quick(self):
        from tools import execute_eurydice_tool_mock
        result = execute_eurydice_tool_mock("audio_analysis", {"mode": "quick"})
        assert result["mode"] == "quick"
        assert "performance_scores" in result

    def test_mock_audio_deep(self):
        from tools import execute_eurydice_tool_mock
        result = execute_eurydice_tool_mock("audio_analysis", {"mode": "deep"})
        assert result["mode"] == "deep"
        assert "note_events" in result

    def test_mock_vision(self):
        from tools import execute_eurydice_tool_mock
        result = execute_eurydice_tool_mock("vision_analysis", {})
        assert "hands_detected" in result
        assert "technique_flags" in result

    def test_mock_coaching_passthrough(self):
        from tools import execute_eurydice_tool_mock
        args = {"observed_issue": "timing", "primary_correction": "fix it", "drill": "do this", "success_criterion": "pass"}
        result = execute_eurydice_tool_mock("coaching_response", args)
        assert result == args

    def test_mock_unknown_tool(self):
        from tools import execute_eurydice_tool_mock
        result = execute_eurydice_tool_mock("unknown_tool", {})
        assert "error" in result

    def test_live_coaching_passthrough(self):
        from tools import execute_eurydice_tool_live
        args = {"observed_issue": "x", "primary_correction": "y", "drill": "z", "success_criterion": "w"}
        result = execute_eurydice_tool_live("coaching_response", args)
        assert result == args

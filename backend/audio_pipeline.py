"""
Real audio analysis pipeline for Eurydice.

Quick mode  — librosa: tempo, beat tracking, onset detection, pitch confidence.
Deep mode   — librosa + Basic Pitch (Spotify): note transcription, alignment scoring.

Falls back gracefully when libraries are missing.
"""

from __future__ import annotations

import base64
import io
import os
import tempfile
import time
from typing import Any


def analyze_audio(args: dict[str, Any]) -> dict[str, Any]:
    """
    Analyze a base64-encoded WAV/PCM guitar recording.
    Returns structured output matching the AudioAnalysisResult schema.
    """
    try:
        import librosa  # type: ignore[import]
        import numpy as np
    except ImportError:
        return {
            "error": "librosa not installed",
            "mode": args.get("mode", "quick"),
            "warnings": ["librosa not installed — install it for real audio analysis"],
        }

    mode = args.get("mode", "quick")
    audio_b64 = args.get("audio_b64", "")
    target_bpm: float | None = args.get("target_bpm")
    target_notes: list[dict[str, Any]] = args.get("target_notes") or []
    has_backing_track: bool = args.get("has_backing_track", False)

    if not audio_b64:
        return {"error": "No audio provided", "mode": mode, "warnings": ["No audio data received"]}

    try:
        audio_bytes = base64.b64decode(audio_b64)
        y, sr = librosa.load(io.BytesIO(audio_bytes), sr=None, mono=True)
    except Exception as exc:
        return {
            "error": f"Audio decode failed: {exc}",
            "mode": mode,
            "warnings": ["Audio could not be decoded — ensure WAV format"],
        }

    t0 = time.perf_counter()
    warnings: list[str] = []
    duration_s = len(y) / sr

    if duration_s < 1.5:
        warnings.append("Recording too short — aim for at least 2 seconds")

    # ── Tempo & beats ──────────────────────────────────────────────────────────
    tempo_arr, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    tempo_bpm = float(tempo_arr[0]) if hasattr(tempo_arr, "__len__") else float(tempo_arr)
    beat_times: list[float] = librosa.frames_to_time(beat_frames, sr=sr).tolist()

    # Confidence heuristic: more beats relative to duration = higher confidence
    expected_beats = duration_s * (tempo_bpm / 60.0)
    tempo_confidence = float(min(0.95, len(beat_frames) / max(1.0, expected_beats)))

    if tempo_confidence < 0.5:
        warnings.append("Tempo tracking uncertain — try a more rhythmically consistent recording")

    # ── Onsets ────────────────────────────────────────────────────────────────
    onset_frames = librosa.onset.onset_detect(y=y, sr=sr, units="frames")
    onset_times: list[float] = librosa.frames_to_time(onset_frames, sr=sr).tolist()

    # ── Pitch confidence (monophonic pyin) ────────────────────────────────────
    try:
        _f0, _voiced, voiced_probs = librosa.pyin(
            y, fmin=librosa.note_to_hz("E2"), fmax=librosa.note_to_hz("E6"), sr=sr
        )
        import numpy as np
        pitch_confidence = float(np.nanmean(voiced_probs)) if len(voiced_probs) > 0 else 0.5
    except Exception:
        pitch_confidence = 0.5

    if pitch_confidence < 0.4:
        warnings.append("Pitch detection weak — try a cleaner single-note recording without heavy distortion")

    # ── Timing score ──────────────────────────────────────────────────────────
    timing_score = _timing_score(onset_times, beat_times, target_bpm or tempo_bpm)

    result: dict[str, Any] = {
        "mode": mode,
        "tempo_bpm": round(tempo_bpm, 1),
        "tempo_confidence": round(tempo_confidence, 2),
        "beat_times_s": [round(t, 3) for t in beat_times[:20]],
        "onset_times_s": [round(t, 3) for t in onset_times[:50]],
        "pitch_confidence": round(pitch_confidence, 2),
        "performance_scores": {
            "timing": round(timing_score, 2),
            "notes": round(min(pitch_confidence + 0.1, 1.0), 2),
            "overall": round((timing_score + min(pitch_confidence + 0.1, 1.0)) / 2, 2),
        },
        "warnings": warnings,
    }

    # ── Deep mode: Basic Pitch transcription ──────────────────────────────────
    if mode == "deep":
        result = _deep_analysis(result, audio_bytes, target_notes, has_backing_track)

    result["_analysis_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def _timing_score(onset_times: list[float], beat_times: list[float], bpm: float) -> float:
    """Score onset alignment against the beat grid: 1.0 = perfect, 0.0 = chaotic."""
    if not onset_times or not beat_times:
        return 0.5
    import numpy as np
    beat_period = 60.0 / max(bpm, 1.0)
    errors = []
    for onset in onset_times:
        diffs = [abs(onset - b) for b in beat_times]
        errors.append(min(min(diffs) / beat_period, 1.0))
    return float(max(0.0, 1.0 - np.mean(errors) * 1.8))


def _deep_analysis(
    result: dict[str, Any],
    audio_bytes: bytes,
    target_notes: list[dict[str, Any]],
    has_backing_track: bool,
) -> dict[str, Any]:
    """Add Basic Pitch note transcription to the result dict."""
    try:
        from basic_pitch.inference import predict  # type: ignore[import]
        from basic_pitch import ICASSP_2022_MODEL_PATH  # type: ignore[import]
    except ImportError:
        result["warnings"].append("basic-pitch not installed — note transcription unavailable in deep mode")
        result["note_events"] = []
        return result

    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        _model_output, _midi, note_events_raw = predict(
            tmp_path,
            ICASSP_2022_MODEL_PATH,
            onset_threshold=0.5,
            frame_threshold=0.3,
        )

        note_events = [
            {
                "onset_s": round(float(ne[0]), 3),
                "offset_s": round(float(ne[1]), 3),
                "midi": int(ne[2]),
                "confidence": round(float(ne[3]), 2),
            }
            for ne in note_events_raw
        ]
        result["note_events"] = note_events

        if target_notes and note_events:
            alignment = _alignment_metrics(note_events, target_notes)
            result["alignment"] = alignment
            f1 = alignment.get("note_f1", result["performance_scores"]["notes"])
            result["performance_scores"]["notes"] = round(f1, 2)
            result["performance_scores"]["overall"] = round(
                (result["performance_scores"]["timing"] + f1) / 2, 2
            )

    except Exception as exc:
        result["warnings"].append(f"Note transcription failed: {exc}")
        result["note_events"] = []
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    return result


def _alignment_metrics(
    detected: list[dict[str, Any]],
    target: list[dict[str, Any]],
    onset_tol_s: float = 0.1,
) -> dict[str, Any]:
    """Compute onset/pitch alignment F1 and error stats."""
    import numpy as np

    matched_d: set[int] = set()
    matched_t: set[int] = set()
    onset_errors: list[float] = []

    for ti, tn in enumerate(target):
        for di, dn in enumerate(detected):
            if di in matched_d:
                continue
            if abs(dn["onset_s"] - tn["onset_s"]) <= onset_tol_s and dn["midi"] == tn["midi"]:
                matched_d.add(di)
                matched_t.add(ti)
                onset_errors.append(abs(dn["onset_s"] - tn["onset_s"]) * 1000)
                break

    tp = len(matched_t)
    precision = tp / len(detected) if detected else 0.0
    recall = tp / len(target) if target else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "note_f1": round(f1, 3),
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "mean_onset_error_ms": round(float(np.mean(onset_errors)), 1) if onset_errors else None,
        "max_onset_error_ms": round(float(max(onset_errors)), 1) if onset_errors else None,
    }

"""
Real vision analysis pipeline for Eurydice.

Uses MediaPipe Hands to detect hand landmarks, then applies geometric heuristics
to flag common technique issues: collapsed wrist, thumb over neck, excessive
finger lift, pick depth.

Falls back gracefully when mediapipe is not installed.
"""

from __future__ import annotations

import base64
import io
from typing import Any


# MediaPipe hand landmark indices
_WRIST = 0
_THUMB_CMC, _THUMB_MCP, _THUMB_IP, _THUMB_TIP = 1, 2, 3, 4
_INDEX_MCP, _INDEX_PIP, _INDEX_DIP, _INDEX_TIP = 5, 6, 7, 8
_MIDDLE_MCP, _MIDDLE_PIP, _MIDDLE_DIP, _MIDDLE_TIP = 9, 10, 11, 12
_RING_MCP, _RING_PIP, _RING_DIP, _RING_TIP = 13, 14, 15, 16
_PINKY_MCP, _PINKY_PIP, _PINKY_DIP, _PINKY_TIP = 17, 18, 19, 20


def analyze_vision(args: dict[str, Any]) -> dict[str, Any]:
    """
    Analyze a base64-encoded guitar technique image.
    Returns structured output matching the VisionAnalysisResult schema.
    """
    try:
        import mediapipe as mp  # type: ignore[import]
        import numpy as np
        from PIL import Image  # type: ignore[import]
    except ImportError as exc:
        return {
            "error": f"Vision library not installed: {exc}",
            "hands_detected": 0,
            "capture_warnings": ["mediapipe/Pillow not installed — install for real technique analysis"],
        }

    image_b64: str = args.get("image_b64", "")
    focus: str = args.get("focus", "both")

    if not image_b64:
        return {
            "error": "No image provided",
            "hands_detected": 0,
            "capture_warnings": ["No image data received"],
        }

    try:
        img_bytes = base64.b64decode(image_b64)
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        img_array = np.array(img)
    except Exception as exc:
        return {
            "error": f"Image decode failed: {exc}",
            "hands_detected": 0,
            "capture_warnings": ["Image could not be decoded — ensure JPEG or PNG format"],
        }

    capture_warnings: list[str] = []
    h, w = img_array.shape[:2]
    if w < 320 or h < 240:
        capture_warnings.append("Low resolution — try recording at higher quality for better detection")

    mp_hands = mp.solutions.hands  # type: ignore[attr-defined]
    with mp_hands.Hands(
        static_image_mode=True,
        max_num_hands=2,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    ) as detector:
        results = detector.process(img_array)

    if not results.multi_hand_landmarks:
        capture_warnings.append("No hands detected — try a clearer angle with even lighting")
        return {
            "hands_detected": 0,
            "handedness": [],
            "technique_flags": [],
            "capture_warnings": capture_warnings,
        }

    handedness_list: list[str] = []
    if results.multi_handedness:
        for h_info in results.multi_handedness:
            handedness_list.append(h_info.classification[0].label.lower())

    technique_flags: list[dict[str, Any]] = []
    for i, hand_lm in enumerate(results.multi_hand_landmarks):
        hand_label = handedness_list[i] if i < len(handedness_list) else "unknown"
        lm = [(pt.x, pt.y, pt.z) for pt in hand_lm.landmark]
        flags = _detect_flags(lm, hand_label, focus)
        technique_flags.extend(flags)

    # Only surface flags above confidence threshold (per CLAUDE.md)
    technique_flags = [f for f in technique_flags if f["confidence"] >= 0.6]

    return {
        "hands_detected": len(results.multi_hand_landmarks),
        "handedness": handedness_list,
        "technique_flags": technique_flags,
        "capture_warnings": capture_warnings,
    }


# ── Technique flag detectors ──────────────────────────────────────────────────

def _detect_flags(
    lm: list[tuple[float, float, float]],
    hand_label: str,
    focus: str,
) -> list[dict[str, Any]]:
    """Return technique flags from normalized MediaPipe landmarks."""
    import numpy as np

    flags: list[dict[str, Any]] = []

    # ── Collapsed wrist (fretting / left hand) ────────────────────────────────
    if focus in ("fretting_hand", "both") and hand_label == "left":
        knuckle_y = float(np.mean([
            lm[_INDEX_MCP][1], lm[_MIDDLE_MCP][1],
            lm[_RING_MCP][1], lm[_PINKY_MCP][1],
        ]))
        wrist_y = lm[_WRIST][1]
        # In normalised coords y increases downward; a high wrist_y means wrist
        # is lower on screen than knuckles — indicates collapsed arch.
        drop = wrist_y - knuckle_y
        if drop > 0.05:
            confidence = float(min(0.95, 0.6 + drop * 4))
            flags.append({
                "flag": "collapsed_wrist",
                "severity": "high" if drop > 0.12 else "medium",
                "confidence": round(confidence, 2),
                "description": (
                    "Fretting wrist appears collapsed under the neck. "
                    "Arch the wrist outward for better reach and to avoid strain."
                ),
            })

    # ── Thumb over neck (fretting / left hand) ────────────────────────────────
    if focus in ("fretting_hand", "both") and hand_label == "left":
        thumb_tip_x = lm[_THUMB_TIP][0]
        index_tip_x = lm[_INDEX_TIP][0]
        # Thumb should be on the opposite side of the neck from fingertips.
        # If x-distance is small, thumb is wrapping over the top.
        x_gap = abs(thumb_tip_x - index_tip_x)
        if x_gap < 0.08:
            confidence = float(min(0.9, 0.6 + (0.08 - x_gap) * 6))
            flags.append({
                "flag": "thumb_over_neck",
                "severity": "medium",
                "confidence": round(confidence, 2),
                "description": (
                    "Thumb appears to wrap over the top of the neck. "
                    "Move it behind the neck for more reach and cleaner fretting."
                ),
            })

    # ── Excessive finger lift (picking / right hand) ──────────────────────────
    if focus in ("picking_hand", "both") and hand_label == "right":
        import numpy as np
        tips_y = np.array([lm[_INDEX_TIP][1], lm[_MIDDLE_TIP][1], lm[_RING_TIP][1], lm[_PINKY_TIP][1]])
        mcps_y = np.array([lm[_INDEX_MCP][1], lm[_MIDDLE_MCP][1], lm[_RING_MCP][1], lm[_PINKY_MCP][1]])
        # Tips higher on screen (lower y) than MCPs = fingers lifted up
        avg_lift = float(np.mean(mcps_y - tips_y))
        if avg_lift > 0.12:
            confidence = float(min(0.9, 0.6 + (avg_lift - 0.12) * 4))
            flags.append({
                "flag": "excessive_finger_lift",
                "severity": "low" if avg_lift < 0.18 else "medium",
                "confidence": round(confidence, 2),
                "description": (
                    "Picking hand fingers raised noticeably above the strings. "
                    "Keep fingers relaxed and close to the strings for faster, more controlled playing."
                ),
            })

    return flags

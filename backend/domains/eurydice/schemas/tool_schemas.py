"""
Eurydice tool declarations for the Claude Messages API.

These are the Anthropic-compatible tool definitions for:
- audio_analysis: guitar performance analysis (quick/deep)
- coaching_response: structured teaching feedback
- vision_analysis: hand/posture technique analysis
"""

from typing import Any


EURYDICE_TOOL_DECLARATIONS: list[dict[str, Any]] = [
    {
        "name": "audio_analysis",
        "description": (
            "Analyze a guitar performance recording. "
            "In 'quick' mode returns tempo, onset timing, and pitch scores quickly. "
            "In 'deep' mode additionally runs note transcription (Basic Pitch) and "
            "optional source separation (Demucs). "
            "Always returns confidence values — if confidence is below 0.7 on any key "
            "metric, report it and ask for a cleaner recording rather than guessing. "
            "Call this tool instead of guessing about the user's playing."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["quick", "deep"],
                    "description": "Analysis depth. Use 'quick' first; escalate to 'deep' if needed.",
                },
                "audio_b64": {
                    "type": "string",
                    "description": "Base64-encoded WAV or PCM audio of the guitar performance.",
                },
                "target_bpm": {
                    "type": "number",
                    "description": "Target tempo in BPM for alignment scoring. Optional.",
                },
                "target_notes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "onset_s": {"type": "number"},
                            "midi": {"type": "integer"},
                        },
                        "required": ["onset_s", "midi"],
                    },
                    "description": "Reference note events for note-level scoring. Optional.",
                },
                "has_backing_track": {
                    "type": "boolean",
                    "description": "Set true if the recording contains a backing track; triggers separation in deep mode.",
                },
            },
            "required": ["mode"],
        },
    },
    {
        "name": "coaching_response",
        "description": (
            "ALWAYS call this tool after audio_analysis (and vision_analysis if used) "
            "to deliver structured teaching feedback. "
            "Do NOT write coaching as plain prose — use this tool every time. "
            "Fill every required field based on the analysis results and the learner's history."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "observed_issue": {
                    "type": "string",
                    "description": "What the analysis measured — be specific, reference timestamps or scores.",
                },
                "likely_cause": {
                    "type": "string",
                    "description": "The probable root cause of the issue.",
                },
                "primary_correction": {
                    "type": "string",
                    "description": "The single highest-leverage fix. One actionable sentence.",
                },
                "drill": {
                    "type": "string",
                    "description": "A specific 20–60 second practice exercise targeting the issue.",
                },
                "success_criterion": {
                    "type": "string",
                    "description": "One clear, measurable condition for the next take to pass.",
                },
                "confidence_note": {
                    "type": "string",
                    "description": "Optional caveat about analysis confidence or capture quality.",
                },
                "mastery_status": {
                    "type": "string",
                    "enum": ["progressing", "close", "mastered"],
                    "description": "'close' = one more pass needed, 'mastered' = gate passed.",
                },
            },
            "required": ["observed_issue", "primary_correction", "drill", "success_criterion"],
        },
    },
    {
        "name": "vision_analysis",
        "description": (
            "Analyze a photograph or video frame of a guitarist's hands/posture. "
            "Returns detected hand landmarks, handedness, and technique flags such as "
            "collapsed_wrist, excessive_finger_lift, thumb_over_neck, or pick_depth. "
            "Each flag includes severity (low/medium/high) and confidence (0–1). "
            "Only report flags whose confidence >= 0.6. "
            "Call this tool when the user shares a camera image for technique feedback."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "image_b64": {
                    "type": "string",
                    "description": "Base64-encoded JPEG or PNG image of the guitarist.",
                },
                "focus": {
                    "type": "string",
                    "enum": ["fretting_hand", "picking_hand", "both", "posture"],
                    "description": "Which aspect to focus the analysis on.",
                },
            },
            "required": ["image_b64"],
        },
    },
]

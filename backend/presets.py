"""
Preset passages for quick-start target selection.

Each preset defines a short guitar phrase with BPM, reference MIDI notes,
and difficulty level. Users can pick a preset instead of manually describing
a target passage.
"""

from __future__ import annotations

from typing import Any


PRESET_PASSAGES: list[dict[str, Any]] = [
    {
        "id": "smoke_on_the_water",
        "description": "Smoke on the Water — opening riff",
        "target_bpm": 112,
        "target_notes": [
            {"onset_s": 0.00, "midi": 55},   # G3
            {"onset_s": 0.27, "midi": 58},   # Bb3
            {"onset_s": 0.54, "midi": 60},   # C4
            {"onset_s": 0.80, "midi": 55},   # G3
            {"onset_s": 1.07, "midi": 58},   # Bb3
            {"onset_s": 1.25, "midi": 61},   # Db4
            {"onset_s": 1.43, "midi": 60},   # C4
        ],
        "difficulty": "beginner",
    },
    {
        "id": "come_as_you_are",
        "description": "Come As You Are — intro riff",
        "target_bpm": 120,
        "target_notes": [
            {"onset_s": 0.00, "midi": 52},   # E3
            {"onset_s": 0.25, "midi": 53},   # F3
            {"onset_s": 0.50, "midi": 55},   # G3
            {"onset_s": 0.75, "midi": 53},   # F3
            {"onset_s": 1.00, "midi": 52},   # E3
            {"onset_s": 1.25, "midi": 53},   # F3
            {"onset_s": 1.50, "midi": 55},   # G3
            {"onset_s": 1.75, "midi": 55},   # G3
        ],
        "difficulty": "beginner",
    },
    {
        "id": "seven_nation_army",
        "description": "Seven Nation Army — main riff",
        "target_bpm": 124,
        "target_notes": [
            {"onset_s": 0.00, "midi": 52},   # E3
            {"onset_s": 0.48, "midi": 52},   # E3
            {"onset_s": 0.73, "midi": 55},   # G3
            {"onset_s": 0.97, "midi": 52},   # E3
            {"onset_s": 1.21, "midi": 50},   # D3
            {"onset_s": 1.69, "midi": 48},   # C3
            {"onset_s": 2.42, "midi": 47},   # B2
        ],
        "difficulty": "beginner",
    },
    {
        "id": "blackbird_opening",
        "description": "Blackbird — opening fingerpicking phrase",
        "target_bpm": 96,
        "target_notes": [
            {"onset_s": 0.00, "midi": 55},   # G3
            {"onset_s": 0.16, "midi": 64},   # E4
            {"onset_s": 0.31, "midi": 67},   # G4
            {"onset_s": 0.47, "midi": 69},   # A4
            {"onset_s": 0.63, "midi": 67},   # G4
            {"onset_s": 0.78, "midi": 64},   # E4
        ],
        "difficulty": "intermediate",
    },
]


def get_preset(preset_id: str) -> dict[str, Any] | None:
    """Look up a preset by ID. Returns None if not found."""
    for p in PRESET_PASSAGES:
        if p["id"] == preset_id:
            return p
    return None


def list_presets() -> list[dict[str, str]]:
    """Return a summary list of available presets (no note data)."""
    return [
        {
            "id": p["id"],
            "description": p["description"],
            "target_bpm": p["target_bpm"],
            "difficulty": p["difficulty"],
        }
        for p in PRESET_PASSAGES
    ]

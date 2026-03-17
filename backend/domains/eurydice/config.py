"""
Eurydice domain configuration.

Centralizes mastery thresholds, difficulty presets, and domain-specific
settings that can be adjusted without changing engine code.
"""

# Mastery gate defaults
CONSECUTIVE_PASSES_REQUIRED = 3
CONFIDENCE_GATE = 0.70

# Difficulty-based threshold adjustments
DIFFICULTY_THRESHOLDS = {
    "beginner": {"timing": 0.75, "notes": 0.70},
    "intermediate": {"timing": 0.85, "notes": 0.80},
    "advanced": {"timing": 0.92, "notes": 0.90},
}

# Capture quality thresholds
CAPTURE_MIN_DURATION_S = 2.0
CAPTURE_NOISE_FLOOR_THRESHOLD = 0.01  # ~-40 dBFS
CAPTURE_CLIPPING_RATIO_THRESHOLD = 0.001

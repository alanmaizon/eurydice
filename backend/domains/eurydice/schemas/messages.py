"""
Eurydice-specific WebSocket message types.

These supplement the generic session contracts with music-teaching-specific
messages: state changes, mastery updates, target validation, capture quality.
"""

from pydantic import BaseModel
from typing import Any, Optional, Literal


class StateChangedMessage(BaseModel):
    type: Literal["session.state"] = "session.state"
    state: str
    previous: Optional[str] = None


class MasteryUpdateMessage(BaseModel):
    type: Literal["mastery.update"] = "mastery.update"
    consecutive_passes: int
    passes_needed: int
    mastered: bool
    gate_detail: Any
    attempt_number: int


class MasteryAchievedMessage(BaseModel):
    type: Literal["mastery.achieved"] = "mastery.achieved"
    total_attempts: int
    passage_description: Optional[str] = None


class AudioRecordingMessage(BaseModel):
    """Full recording buffer (base64 WAV) — distinct from the streaming input.audio."""
    type: Literal["input.audio_recording"]
    audio_b64: str
    duration_s: Optional[float] = None


class TargetSetMessage(BaseModel):
    """User defines the target passage before recording."""
    type: Literal["target.set"]
    description: str = ""
    target_bpm: Optional[float] = None
    target_notes: Optional[list[Any]] = None
    difficulty: str = "beginner"
    preset_id: Optional[str] = None


class TargetValidationMessage(BaseModel):
    type: Literal["target.validation"] = "target.validation"
    valid: bool
    errors: list[str] = []
    warnings: list[str] = []


class CaptureInvalidMessage(BaseModel):
    type: Literal["capture.invalid"] = "capture.invalid"
    analysis_confidence: float
    capture_quality: str = "unknown"
    reasons: list[str] = []


class UserDisagreementMessage(BaseModel):
    type: Literal["user.disagreement"] = "user.disagreement"
    attempt_number: int
    reason: str = ""

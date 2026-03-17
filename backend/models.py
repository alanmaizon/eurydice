from pydantic import BaseModel
from typing import Any, Optional, Literal


# ── Client → Server ──────────────────────────────────────────────────────────

class SessionConfig(BaseModel):
    system_instruction: str
    voice: Optional[str] = None


class SessionStartMessage(BaseModel):
    type: Literal["session.start"]
    config: SessionConfig


class SessionEndMessage(BaseModel):
    type: Literal["session.end"]


class TextInputMessage(BaseModel):
    type: Literal["input.text"]
    text: str


class AudioInputMessage(BaseModel):
    type: Literal["input.audio"]
    audio: str  # base64 PCM 16-bit 16kHz mono


class ImageInputMessage(BaseModel):
    type: Literal["input.image"]
    image: str  # base64
    mime_type: str = "image/jpeg"


class InterruptMessage(BaseModel):
    type: Literal["input.interrupt"]


# ── Server → Client ──────────────────────────────────────────────────────────

class SessionStartedMessage(BaseModel):
    type: Literal["session.started"] = "session.started"
    session_id: str


class SessionEndedMessage(BaseModel):
    type: Literal["session.ended"] = "session.ended"


class TextDeltaMessage(BaseModel):
    type: Literal["output.text.delta"] = "output.text.delta"
    delta: str


class TextDoneMessage(BaseModel):
    type: Literal["output.text.done"] = "output.text.done"
    full_text: str


class AudioDeltaMessage(BaseModel):
    type: Literal["output.audio.delta"] = "output.audio.delta"
    audio: str  # base64 PCM


class AudioDoneMessage(BaseModel):
    type: Literal["output.audio.done"] = "output.audio.done"


class ToolCallMessage(BaseModel):
    type: Literal["tool.call"] = "tool.call"
    tool_name: str
    args: dict[str, Any]
    call_id: str


class ToolResultMessage(BaseModel):
    type: Literal["tool.result"] = "tool.result"
    call_id: str
    result: Any


class ErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    message: str
    code: Optional[str] = None


class StatusMessage(BaseModel):
    type: Literal["status"] = "status"
    state: Literal["connecting", "live", "error", "ended"]


class LogMessage(BaseModel):
    type: Literal["log"] = "log"
    event: str
    data: Optional[Any] = None
    timestamp: Optional[str] = None

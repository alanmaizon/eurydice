"""Typed websocket protocol for the scaffold `/ws/live` contract."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator

from ..schemas import TutorMode


LIVE_PROTOCOL_VERSION = "2026-03-15"
INPUT_AUDIO_MIME_TYPE = "audio/pcm;rate=16000"
OUTPUT_AUDIO_MIME_TYPE = "audio/pcm;rate=24000"
ACCEPTED_IMAGE_MIME_TYPES = ["image/jpeg", "image/png", "image/webp"]

CLIENT_EVENT_TYPES = [
    "client.hello",
    "client.input.text",
    "client.input.audio",
    "client.input.image",
    "client.turn.end",
    "client.control.interrupt",
    "client.control.ping",
]

SERVER_EVENT_TYPES = [
    "server.ready",
    "server.status",
    "server.transcript",
    "server.output.text",
    "server.output.audio",
    "server.tool.call",
    "server.tool.result",
    "server.turn",
    "server.session.update",
    "server.error",
]


class LiveEventBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    protocol_version: str = LIVE_PROTOCOL_VERSION


class ClientCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audio_input: bool = True
    audio_output: bool = True
    image_input: bool = True
    supports_barge_in: bool = True


class ClientHelloEvent(LiveEventBase):
    type: Literal["client.hello"] = "client.hello"
    session_id: str | None = None
    mode: TutorMode | None = None
    target_text: str | None = None
    preferred_response_language: str | None = None
    gemini_api_key: str | None = None
    capabilities: ClientCapabilities = Field(default_factory=ClientCapabilities)
    client_name: str = "frontend"


class ClientTextInputEvent(LiveEventBase):
    type: Literal["client.input.text"] = "client.input.text"
    turn_id: str
    text: str = Field(min_length=1)
    source: Literal["typed", "ocr", "transcript_correction"] = "typed"
    is_final: bool = True


class ClientAudioInputEvent(LiveEventBase):
    type: Literal["client.input.audio"] = "client.input.audio"
    turn_id: str
    chunk_index: int = Field(ge=0)
    mime_type: str = INPUT_AUDIO_MIME_TYPE
    data_base64: str = Field(min_length=1)
    is_final_chunk: bool = False

    @field_validator("mime_type")
    @classmethod
    def validate_audio_mime_type(cls, value: str) -> str:
        if not value.startswith("audio/pcm;rate="):
            raise ValueError("client.input.audio must use audio/pcm with an explicit rate")
        return value


class ClientImageInputEvent(LiveEventBase):
    type: Literal["client.input.image"] = "client.input.image"
    turn_id: str
    frame_index: int = Field(ge=0)
    mime_type: Literal["image/jpeg", "image/png", "image/webp"]
    source: Literal["camera_frame", "worksheet_upload"] = "camera_frame"
    data_base64: str = Field(min_length=1)
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    is_reference: bool = False


class ClientTurnEndEvent(LiveEventBase):
    type: Literal["client.turn.end"] = "client.turn.end"
    turn_id: str
    reason: Literal["done", "silence_timeout", "submit_click", "stop_recording"] = "done"


class ClientInterruptEvent(LiveEventBase):
    type: Literal["client.control.interrupt"] = "client.control.interrupt"
    turn_id: str | None = None
    reason: Literal["barge_in", "stop_button", "navigation", "connection_reset"] = "stop_button"


class ClientPingEvent(LiveEventBase):
    type: Literal["client.control.ping"] = "client.control.ping"
    client_time: str | None = None


LiveClientEvent = Annotated[
    (
        ClientHelloEvent
        | ClientTextInputEvent
        | ClientAudioInputEvent
        | ClientImageInputEvent
        | ClientTurnEndEvent
        | ClientInterruptEvent
        | ClientPingEvent
    ),
    Field(discriminator="type"),
]


class ServerReadyEvent(LiveEventBase):
    type: Literal["server.ready"] = "server.ready"
    connection_id: str
    websocket_path: str
    accepted_client_events: list[str] = Field(default_factory=lambda: list(CLIENT_EVENT_TYPES))
    emitted_server_events: list[str] = Field(default_factory=lambda: list(SERVER_EVENT_TYPES))
    input_audio_mime_type: str = INPUT_AUDIO_MIME_TYPE
    output_audio_mime_type: str = OUTPUT_AUDIO_MIME_TYPE
    accepted_image_mime_types: list[str] = Field(default_factory=lambda: list(ACCEPTED_IMAGE_MIME_TYPES))
    supports_session_resumption: bool = True
    notes: str = (
        "After connect, send client.hello. Then stream client.input.* events grouped by turn_id "
        "and close the learner turn with client.turn.end."
    )


class ServerStatusEvent(LiveEventBase):
    type: Literal["server.status"] = "server.status"
    phase: Literal[
        "ready",
        "listening",
        "receiving_input",
        "thinking",
        "tool_running",
        "speaking",
        "interrupted",
        "closing",
        "closed",
        "error",
    ]
    detail: str
    session_id: str | None = None
    turn_id: str | None = None
    resumable: bool | None = None


class ServerTranscriptEvent(LiveEventBase):
    type: Literal["server.transcript"] = "server.transcript"
    session_id: str
    turn_id: str
    speaker: Literal["learner", "tutor"]
    source: Literal["input_text", "input_audio", "output_text", "output_audio_transcription"]
    text: str = Field(min_length=1)
    is_final: bool = False
    interrupted: bool = False


class ServerTextOutputEvent(LiveEventBase):
    type: Literal["server.output.text"] = "server.output.text"
    session_id: str
    turn_id: str
    text: str = Field(min_length=1)
    is_final: bool = False


class ServerAudioOutputEvent(LiveEventBase):
    type: Literal["server.output.audio"] = "server.output.audio"
    session_id: str
    turn_id: str
    chunk_index: int = Field(ge=0)
    mime_type: str = OUTPUT_AUDIO_MIME_TYPE
    data_base64: str = Field(min_length=1)
    is_final_chunk: bool = False

    @field_validator("mime_type")
    @classmethod
    def validate_audio_mime_type(cls, value: str) -> str:
        if not value.startswith("audio/pcm;rate="):
            raise ValueError("server.output.audio must use audio/pcm with an explicit rate")
        return value


class ServerToolCallEvent(LiveEventBase):
    type: Literal["server.tool.call"] = "server.tool.call"
    session_id: str
    turn_id: str
    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: Literal["requested", "started"] = "requested"


class ServerToolResultEvent(LiveEventBase):
    type: Literal["server.tool.result"] = "server.tool.result"
    session_id: str
    turn_id: str
    tool_call_id: str
    tool_name: str
    status: Literal["completed", "failed"] = "completed"
    result: dict[str, Any] | None = None
    error: str | None = None


class ServerTurnEvent(LiveEventBase):
    type: Literal["server.turn"] = "server.turn"
    session_id: str
    turn_id: str
    event: Literal["learner_turn_closed", "generation_complete", "turn_complete", "interrupted"]
    detail: str | None = None


class ServerSessionUpdateEvent(LiveEventBase):
    type: Literal["server.session.update"] = "server.session.update"
    session_id: str | None = None
    resumption_handle: str | None = None
    go_away: bool = False
    time_left_ms: int | None = Field(default=None, ge=0)
    context_window_compression: bool | None = None


class ServerErrorEvent(LiveEventBase):
    type: Literal["server.error"] = "server.error"
    code: str
    message: str
    retryable: bool = False
    session_id: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


LiveServerEvent = Annotated[
    (
        ServerReadyEvent
        | ServerStatusEvent
        | ServerTranscriptEvent
        | ServerTextOutputEvent
        | ServerAudioOutputEvent
        | ServerToolCallEvent
        | ServerToolResultEvent
        | ServerTurnEvent
        | ServerSessionUpdateEvent
        | ServerErrorEvent
    ),
    Field(discriminator="type"),
]


_CLIENT_EVENT_ADAPTER = TypeAdapter(LiveClientEvent)
_SERVER_EVENT_ADAPTER = TypeAdapter(LiveServerEvent)


def parse_client_event(raw_event: Any) -> LiveClientEvent:
    return _CLIENT_EVENT_ADAPTER.validate_python(raw_event)


def parse_server_event(raw_event: Any) -> LiveServerEvent:
    return _SERVER_EVENT_ADAPTER.validate_python(raw_event)


def build_server_ready_event(connection_id: str, websocket_path: str) -> ServerReadyEvent:
    return ServerReadyEvent(connection_id=connection_id, websocket_path=websocket_path)


def build_server_error_event(
    code: str,
    message: str,
    *,
    retryable: bool = False,
    session_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> ServerErrorEvent:
    return ServerErrorEvent(
        code=code,
        message=message,
        retryable=retryable,
        session_id=session_id,
        detail=detail or {},
    )


def event_to_wire(event: LiveServerEvent) -> dict[str, Any]:
    return event.model_dump(mode="json", exclude_none=True)


def protocol_contract_summary() -> dict[str, Any]:
    return {
        "protocol_version": LIVE_PROTOCOL_VERSION,
        "accepted_client_events": list(CLIENT_EVENT_TYPES),
        "emitted_server_events": list(SERVER_EVENT_TYPES),
        "input_audio_mime_type": INPUT_AUDIO_MIME_TYPE,
        "output_audio_mime_type": OUTPUT_AUDIO_MIME_TYPE,
        "accepted_image_mime_types": list(ACCEPTED_IMAGE_MIME_TYPES),
        "supports_session_resumption": True,
    }


__all__ = [
    "ACCEPTED_IMAGE_MIME_TYPES",
    "CLIENT_EVENT_TYPES",
    "ClientAudioInputEvent",
    "ClientHelloEvent",
    "ClientImageInputEvent",
    "ClientInterruptEvent",
    "ClientPingEvent",
    "ClientTextInputEvent",
    "ClientTurnEndEvent",
    "INPUT_AUDIO_MIME_TYPE",
    "LIVE_PROTOCOL_VERSION",
    "OUTPUT_AUDIO_MIME_TYPE",
    "SERVER_EVENT_TYPES",
    "ServerErrorEvent",
    "ServerReadyEvent",
    "ServerStatusEvent",
    "ServerTextOutputEvent",
    "ServerToolCallEvent",
    "ServerToolResultEvent",
    "ServerTranscriptEvent",
    "ServerTurnEvent",
    "build_server_error_event",
    "build_server_ready_event",
    "event_to_wire",
    "parse_client_event",
    "parse_server_event",
    "protocol_contract_summary",
    "ValidationError",
]

"""Gemini Live planning and transport layer."""

from __future__ import annotations

import os
from collections.abc import Awaitable
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any

from ..schemas import LiveSessionPlan, SessionBootstrapRequest, ToolDefinition
from ..settings import Settings
from .protocol import protocol_contract_summary


def _resolve_api_key(settings: Settings) -> str | None:
    return (
        settings.gemini_api_key
        or os.getenv("TUTOR_GEMINI_API_KEY")
        or os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
    )


@dataclass
class GeminiLiveConnection:
    """Thin wrapper around a connected `google.genai` live session."""

    _context_manager: AbstractAsyncContextManager[Any]
    _session: Any
    _supports_explicit_activity_end: bool
    _types: Any
    _pending_client_content: bool = False

    async def receive(self) -> AsyncIterator[Any]:
        async for message in self._session.receive():
            yield message

    async def send_text(self, text: str) -> None:
        normalized = text.strip()
        if not normalized:
            return
        await self._session.send_client_content(
            turns={"role": "user", "parts": [{"text": normalized}]},
            turn_complete=False,
        )
        self._pending_client_content = True

    async def send_audio_chunk(
        self,
        *,
        audio_bytes: bytes,
        mime_type: str,
        is_final_chunk: bool,
    ) -> None:
        blob = self._types.Blob(data=audio_bytes, mime_type=mime_type)
        _ = is_final_chunk
        await self._session.send_realtime_input(audio=blob)

    async def end_audio_stream(self) -> None:
        await self._session.send_realtime_input(audio_stream_end=True)

    async def send_image_chunk(
        self,
        *,
        image_bytes: bytes,
        mime_type: str,
    ) -> None:
        blob = self._types.Blob(data=image_bytes, mime_type=mime_type)
        await self._session.send_realtime_input(media=blob)

    async def end_turn(self) -> None:
        if self._pending_client_content:
            await self._session.send_client_content(turn_complete=True)
            self._pending_client_content = False
            return
        if not self._supports_explicit_activity_end:
            return
        await self._session.send_realtime_input(activity_end=self._types.ActivityEnd())

    async def send_tool_response(
        self,
        *,
        tool_call_id: str,
        tool_name: str,
        response: dict[str, Any],
    ) -> None:
        function_response = self._types.FunctionResponse(
            id=tool_call_id,
            name=tool_name,
            response=response,
        )
        await self._session.send_tool_response(function_responses=[function_response])

    async def interrupt(self) -> None:
        """Best-effort interruption for an in-flight model response."""
        interrupt_fn = getattr(self._session, "interrupt", None)
        if callable(interrupt_fn):
            maybe_awaitable = interrupt_fn()
            if isinstance(maybe_awaitable, Awaitable):
                await maybe_awaitable
            return

        # Fallback: signal activity end when explicit interrupt is unavailable.
        if self._supports_explicit_activity_end:
            await self._session.send_realtime_input(activity_end=self._types.ActivityEnd())
            return

        # Last-resort fallback for older SDKs.
        await self.end_turn()

    async def close(self) -> None:
        await self._context_manager.__aexit__(None, None, None)


class GeminiLiveGateway:
    """Seam for Gemini Live integration and runtime connection setup."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @staticmethod
    def sdk_status() -> dict[str, Any]:
        try:
            import google.genai  # type: ignore  # noqa: F401
        except ImportError:
            return {"available": False, "detail": "google-genai is not installed yet"}
        return {"available": True, "detail": "google-genai import succeeded"}

    def credentials_status(self) -> dict[str, Any]:
        api_key = _resolve_api_key(self._settings)
        if api_key:
            return {"available": True, "detail": "API key auth available", "mode": "api_key"}
        if self._settings.google_cloud_project:
            return {"available": True, "detail": "Vertex AI auth available", "mode": "vertex_ai"}
        return {
            "available": False,
            "detail": (
                "No Gemini credentials configured. Set TUTOR_GEMINI_API_KEY (or GEMINI_API_KEY) "
                "or configure TUTOR_GOOGLE_CLOUD_PROJECT for Vertex AI mode."
            ),
            "mode": "none",
        }

    async def connect_session(
        self,
        *,
        system_prompt: str,
        tools: list[ToolDefinition],
    ) -> GeminiLiveConnection:
        try:
            from google import genai  # type: ignore
            from google.genai import types  # type: ignore
        except ImportError as exc:
            raise RuntimeError("google-genai is not installed in this environment") from exc

        creds = self.credentials_status()
        if not creds["available"]:
            raise RuntimeError(str(creds["detail"]))

        api_key = _resolve_api_key(self._settings)
        if api_key:
            client = genai.Client(api_key=api_key)
        else:
            client = genai.Client(
                vertexai=True,
                project=self._settings.google_cloud_project,
                location=self._settings.google_cloud_location,
            )

        declarations = [
            types.FunctionDeclaration(
                name=tool.name,
                description=tool.description,
                parameters_json_schema=tool.input_schema or {"type": "object", "properties": {}},
            )
            for tool in tools
        ]
        session_resumption_config = None
        if creds.get("mode") == "vertex_ai":
            # Vertex supports explicit transparent resumption control.
            session_resumption_config = types.SessionResumptionConfig(transparent=True)
        connect_config = types.LiveConnectConfig(
            system_instruction=system_prompt,
            response_modalities=[types.Modality.AUDIO],
            tools=[types.Tool(function_declarations=declarations)] if declarations else None,
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            session_resumption=session_resumption_config,
        )
        context_manager = client.aio.live.connect(
            model=self._settings.gemini_live_model,
            config=connect_config,
        )
        session = await context_manager.__aenter__()
        return GeminiLiveConnection(
            _context_manager=context_manager,
            _session=session,
            _supports_explicit_activity_end=hasattr(types, "ActivityEnd"),
            _types=types,
        )

    def build_session_plan(
        self,
        request: SessionBootstrapRequest,
        system_prompt: str,
    ) -> LiveSessionPlan:
        contract = protocol_contract_summary()
        media_summary = []
        if request.microphone_ready:
            media_summary.append("microphone")
        if request.camera_ready or request.worksheet_attached:
            media_summary.append("visual input")

        creds = self.credentials_status()
        notes = (
            "Gemini Live bridge is wired. The websocket will attempt upstream connection after "
            "client.hello; if credentials are missing it falls back to scaffold mode with error events. "
            f"Credential status: {creds['detail']}."
        )
        if media_summary:
            notes = f"{notes} Prepared media: {', '.join(media_summary)}."

        return LiveSessionPlan(
            model=self._settings.gemini_live_model,
            websocket_path=self._settings.websocket_path,
            protocol_version=contract["protocol_version"],
            accepted_client_events=contract["accepted_client_events"],
            emitted_server_events=contract["emitted_server_events"],
            input_audio_mime_type=contract["input_audio_mime_type"],
            output_audio_mime_type=contract["output_audio_mime_type"],
            accepted_image_mime_types=contract["accepted_image_mime_types"],
            supports_session_resumption=contract["supports_session_resumption"],
            notes=notes,
        )

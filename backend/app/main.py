"""FastAPI entrypoint for the Ancient Greek live tutor scaffold."""

from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import json
import logging
import re
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .agents.orchestration.live_turns import LiveTurnInput, LiveTurnOrchestrator
from .agents.prompts import build_system_prompt
from .agents.tools.reference import looks_like_reference_request
from .agents.tools import ToolExecutionError, build_default_tool_registry, execute_tool_call
from .api.router import api_router
from .api.routes.health import router as health_router
from .live.gemini_live import GeminiLiveConnection, GeminiLiveGateway
from .live.protocol import (
    ClientAudioInputEvent,
    ClientHelloEvent,
    ClientImageInputEvent,
    ClientInterruptEvent,
    ClientPingEvent,
    ClientTextInputEvent,
    ClientTurnEndEvent,
    OUTPUT_AUDIO_MIME_TYPE,
    ServerAudioOutputEvent,
    ServerSessionUpdateEvent,
    ServerStatusEvent,
    ServerTextOutputEvent,
    ServerToolCallEvent,
    ServerToolResultEvent,
    ServerTranscriptEvent,
    ServerTurnEvent,
    ValidationError,
    build_server_error_event,
    build_server_ready_event,
    event_to_wire,
    parse_client_event,
)
from .settings import get_settings


logger = logging.getLogger("ancient_greek.live")
settings = get_settings()
gemini_gateway = GeminiLiveGateway(settings)
tool_registry = build_default_tool_registry()
turn_orchestrator = LiveTurnOrchestrator(settings)

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(levelname)s %(name)s %(message)s",
)

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    summary="Scaffold for a voice-first multimodal Ancient Greek tutor.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(api_router)

_SECONDS_DURATION_RE = re.compile(r"^(?P<seconds>\d+(?:\.\d+)?)s$")
_MAX_SESSION_MESSAGE_CHARS = 1200
_TURN_FIRST_OUTPUT_TIMEOUT_SECONDS = 18.0
_ANALYSIS_REQUEST_MARKERS = (
    "analysis",
    "analy",
    "parse",
    "parsing",
    "morph",
    "morphology",
    "ending",
    "case",
    "declension",
    "syntax",
)
_FOCUS_WORD_STOPWORDS = {
    "analysis",
    "analyze",
    "and",
    "case",
    "clause",
    "declension",
    "ending",
    "explain",
    "first",
    "for",
    "give",
    "hint",
    "it",
    "look",
    "morph",
    "morphology",
    "of",
    "parse",
    "please",
    "read",
    "show",
    "syntax",
    "that",
    "the",
    "this",
    "translate",
    "translation",
    "word",
}


def _decode_base64_payload(payload: str, *, field_name: str) -> bytes:
    try:
        return base64.b64decode(payload, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError(f"{field_name} is not valid base64") from exc


def _parse_duration_to_ms(duration: str | None) -> int | None:
    if not duration:
        return None
    match = _SECONDS_DURATION_RE.match(duration.strip())
    if not match:
        return None
    return int(float(match.group("seconds")) * 1000)


def _normalize_function_args(raw_args: Any) -> dict[str, Any]:
    if isinstance(raw_args, dict):
        return raw_args
    if isinstance(raw_args, str):
        try:
            parsed = json.loads(raw_args)
        except json.JSONDecodeError:
            return {"raw_args": raw_args}
        if isinstance(parsed, dict):
            return parsed
        return {"raw_args": parsed}
    return {"raw_args": raw_args}


def _compact_text(text: str) -> str:
    return " ".join(text.split()).strip()


def _merge_streaming_text(previous_text: str, incoming_text: str) -> str:
    previous = previous_text.rstrip()
    incoming = _compact_text(incoming_text)

    if not previous:
        return incoming
    if not incoming:
        return previous
    if incoming.startswith(previous):
        return incoming
    if previous.endswith(incoming):
        return previous
    if re.match(r"^[,.;:!?)]", incoming) or re.search(r"[\s([{\"'`-]$", previous):
        return f"{previous}{incoming}"
    return f"{previous} {incoming}"


def _is_read_request(text: str) -> bool:
    normalized = _compact_text(text).lower()
    return any(
        phrase in normalized
        for phrase in (
            "can you read it",
            "read it",
            "read that",
            "read this",
            "please read it",
            "could you read it",
        )
    )


def _looks_like_analysis_request(text: str) -> bool:
    normalized = _compact_text(text).lower()
    return any(marker in normalized for marker in _ANALYSIS_REQUEST_MARKERS)


def _extract_focus_word_hint(text: str) -> str | None:
    if not text:
        return None
    candidates = re.findall(r"[0-9A-Za-z\u0370-\u03ff\u1f00-\u1fff]+", text)
    for candidate in reversed(candidates):
        normalized = _compact_text(candidate).lower()
        if len(normalized) <= 1:
            continue
        if normalized in _FOCUS_WORD_STOPWORDS:
            continue
        return candidate
    return None


def _normalize_preflight_tool_arguments(
    tool_name: str,
    raw_arguments: dict[str, Any],
    *,
    learner_text: str,
    target_text: str | None,
    preferred_response_language: str,
    mode: Any,
) -> dict[str, Any]:
    arguments = dict(raw_arguments)
    compact_learner_text = _compact_text(learner_text)
    compact_target_text = _compact_text(target_text or "")

    if tool_name == "resolve_reference":
        reference_value = arguments.get("reference")
        reference = _compact_text(str(reference_value)) if reference_value is not None else ""
        if not reference:
            reference = compact_learner_text
        if reference:
            arguments["reference"] = reference
        arguments.setdefault("preferred_translation_language", preferred_response_language)
        return arguments

    if tool_name == "parse_passage":
        provided_text_value = arguments.get("text")
        provided_text = (
            _compact_text(str(provided_text_value)) if provided_text_value is not None else ""
        )
        if compact_target_text and (
            not provided_text or provided_text.casefold() == compact_learner_text.casefold()
        ):
            arguments["text"] = compact_target_text
        elif provided_text:
            arguments["text"] = provided_text
        elif compact_target_text:
            arguments["text"] = compact_target_text
        elif compact_learner_text:
            arguments["text"] = compact_learner_text

        focus_word_value = arguments.get("focus_word")
        focus_word = _compact_text(str(focus_word_value)) if focus_word_value is not None else ""
        if not focus_word:
            inferred_focus = _extract_focus_word_hint(compact_learner_text)
            if inferred_focus and inferred_focus.casefold() != compact_learner_text.casefold():
                arguments["focus_word"] = inferred_focus
        else:
            arguments["focus_word"] = focus_word
        return arguments

    if tool_name == "grade_attempt":
        learner_answer_value = arguments.get("learner_answer")
        learner_answer = (
            _compact_text(str(learner_answer_value)) if learner_answer_value is not None else ""
        )
        reference_answer_value = arguments.get("reference_answer")
        reference_answer = (
            _compact_text(str(reference_answer_value))
            if reference_answer_value is not None
            else ""
        )
        if not learner_answer and compact_learner_text:
            arguments["learner_answer"] = compact_learner_text
        elif learner_answer:
            arguments["learner_answer"] = learner_answer
        if not reference_answer and compact_target_text:
            arguments["reference_answer"] = compact_target_text
        elif reference_answer:
            arguments["reference_answer"] = reference_answer
        return arguments

    if tool_name == "generate_drill":
        mistake_summary_value = arguments.get("mistake_summary")
        mistake_summary = (
            _compact_text(str(mistake_summary_value)) if mistake_summary_value is not None else ""
        )
        if not mistake_summary:
            arguments["mistake_summary"] = compact_learner_text or "Learner requested more practice."
        else:
            arguments["mistake_summary"] = mistake_summary
        arguments.setdefault("mode", getattr(mode, "value", str(mode)))
        return arguments

    return arguments


def _append_message(
    memory: list[dict[str, str]],
    *,
    role: str,
    turn_id: str,
    text: str,
) -> None:
    compact_text = _compact_text(text)
    if not compact_text:
        return
    memory.append(
        {
            "role": role,
            "turn_id": turn_id,
            "content": compact_text[:_MAX_SESSION_MESSAGE_CHARS],
        }
    )


def add_user_message(messages: list[dict[str, str]], text: str, *, turn_id: str) -> None:
    _append_message(messages, role="user", turn_id=turn_id, text=text)


def add_assistant_message(messages: list[dict[str, str]], text: str, *, turn_id: str) -> None:
    _append_message(messages, role="assistant", turn_id=turn_id, text=text)


def _build_session_context_message(
    *,
    history: list[dict[str, str]],
    mode: str,
    target_reference: str | None,
    target_text: str | None,
    preferred_response_language: str,
) -> str:
    if not history:
        return ""

    dialogue_lines = []
    for item in history:
        label = "Learner" if item.get("role") == "user" else "Tutor"
        dialogue_lines.append(f"- {label}: {item.get('content', '')}")
    full_dialogue = "\n".join(dialogue_lines)

    reference_line = (
        f"Target passage reference: {target_reference}"
        if target_reference
        else "Target passage reference: (none)"
    )
    target_line = f"Target passage text: {target_text}" if target_text else "Target passage text: (none)"
    return (
        "[session_context]\n"
        "Use the full in-session dialogue history below when answering.\n"
        f"Tutoring mode: {mode}\n"
        f"Preferred explanation language: {preferred_response_language}\n"
        f"{reference_line}\n"
        f"{target_line}\n"
        "Conversation history (oldest to newest):\n"
        f"{full_dialogue}\n"
        "[/session_context]\n"
        "Respond to the most recent learner message."
    )


def _build_orchestration_context_payload(
    *,
    tool_name: str,
    tool_result: dict[str, Any],
    turn_id: str,
) -> dict[str, Any]:
    return {
        "source": "live_turn_orchestrator",
        "turn_id": turn_id,
        "tool_name": tool_name,
        "tool_result": tool_result,
    }


async def send_live_event(
    websocket: WebSocket,
    event: object,
    *,
    send_lock: asyncio.Lock,
) -> None:
    if not hasattr(event, "model_dump"):
        raise TypeError("Expected a live event model")
    payload = event_to_wire(event)
    async with send_lock:
        await websocket.send_json(payload)


@app.get("/", tags=["root"])
def root() -> dict[str, str]:
    return {
        "service": settings.app_name,
        "status": "scaffold",
        "docs": "/docs",
        "health": "/health",
        "runtime": "/api/runtime",
    }


@app.websocket(settings.websocket_path)
async def live_websocket(websocket: WebSocket) -> None:
    await websocket.accept()

    send_lock = asyncio.Lock()
    connection_id = f"conn-{uuid4().hex[:10]}"
    state = {
        "session_id": None,
        "last_turn_id": "turn-initial",
        "active_generation_turn_id": None,
        "audio_chunk_index": 0,
        "mode": settings.default_tutoring_mode,
        "target_text": None,
        "target_reference": None,
        "preferred_response_language": "English",
        "pending_reference": None,
    }
    turn_buffers: dict[str, dict[str, Any]] = {}
    session_memory: list[dict[str, str]] = []
    learner_audio_memory_buffers: dict[str, str] = {}
    committed_learner_turn_ids: set[str] = set()
    tutor_memory_buffers: dict[str, str] = {}
    tutor_audio_turn_ids: set[str] = set()
    turn_first_output_watchdogs: dict[str, asyncio.Task[None]] = {}

    gemini_connection: GeminiLiveConnection | None = None
    gemini_receive_task: asyncio.Task[None] | None = None

    async def emit(event: object) -> None:
        await send_live_event(websocket, event, send_lock=send_lock)

    async def close_gemini_connection() -> None:
        nonlocal gemini_connection, gemini_receive_task

        if gemini_receive_task is not None:
            gemini_receive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await gemini_receive_task
            gemini_receive_task = None

        if gemini_connection is not None:
            try:
                await gemini_connection.close()
            finally:
                gemini_connection = None

        for watchdog in turn_first_output_watchdogs.values():
            watchdog.cancel()
        turn_first_output_watchdogs.clear()

    def flush_tutor_memory(turn_id: str) -> None:
        buffered = tutor_memory_buffers.pop(turn_id, "")
        tutor_audio_turn_ids.discard(turn_id)
        if buffered:
            add_assistant_message(session_memory, buffered, turn_id=turn_id)

    def commit_learner_memory(turn_id: str, text: str) -> None:
        if turn_id in committed_learner_turn_ids:
            return
        compact_text = _compact_text(text)
        if not compact_text:
            return
        add_user_message(session_memory, compact_text, turn_id=turn_id)
        committed_learner_turn_ids.add(turn_id)
        learner_audio_memory_buffers.pop(turn_id, None)

    async def emit_local_tutor_reply(turn_id: str, text: str) -> None:
        compact_text = _compact_text(text)
        if not compact_text:
            return
        await emit(
            ServerTextOutputEvent(
                session_id=state["session_id"] or "session-unknown",
                turn_id=turn_id,
                text=compact_text,
                is_final=True,
            )
        )
        await emit(
            ServerTranscriptEvent(
                session_id=state["session_id"] or "session-unknown",
                turn_id=turn_id,
                speaker="tutor",
                source="output_text",
                text=compact_text,
                is_final=True,
                interrupted=False,
            )
        )
        add_assistant_message(session_memory, compact_text, turn_id=turn_id)
        await emit(
            ServerTurnEvent(
                session_id=state["session_id"] or "session-unknown",
                turn_id=turn_id,
                event="turn_complete",
                detail="Backend satisfied this turn locally without an upstream generation.",
            )
        )

    def apply_tool_side_effects(tool_name: str, tool_result: dict[str, Any]) -> None:
        if tool_name != "resolve_reference" or tool_result.get("status") != "ok":
            return

        resolved_text = str(tool_result.get("resolved_text", "")).strip()
        normalized_reference = str(tool_result.get("normalized_reference", "")).strip()
        if not resolved_text:
            return

        state["target_text"] = resolved_text
        state["target_reference"] = normalized_reference or state["target_reference"]
        state["pending_reference"] = None

    def cancel_turn_first_output_watchdog(turn_id: str) -> None:
        watchdog = turn_first_output_watchdogs.pop(turn_id, None)
        if watchdog is not None:
            watchdog.cancel()

    def mark_turn_completed(turn_id: str) -> None:
        cancel_turn_first_output_watchdog(turn_id)
        if state["active_generation_turn_id"] == turn_id:
            state["active_generation_turn_id"] = None

    def arm_turn_first_output_watchdog(turn_id: str) -> None:
        cancel_turn_first_output_watchdog(turn_id)

        async def watchdog() -> None:
            await asyncio.sleep(_TURN_FIRST_OUTPUT_TIMEOUT_SECONDS)
            turn_first_output_watchdogs.pop(turn_id, None)
            if state["active_generation_turn_id"] != turn_id:
                return
            state["active_generation_turn_id"] = None
            await emit(
                build_server_error_event(
                    "TURN_TIMEOUT",
                    (
                        "Tutor response timed out for this turn. "
                        "Try sending the turn again or reconnecting."
                    ),
                    retryable=True,
                    session_id=state["session_id"],
                    detail={"turn_id": turn_id},
                )
            )
            await emit(
                ServerTurnEvent(
                    session_id=state["session_id"] or "session-unknown",
                    turn_id=turn_id,
                    event="turn_complete",
                    detail="Tutor turn closed after timing out while waiting for model output.",
                )
            )
            flush_tutor_memory(turn_id)

        turn_first_output_watchdogs[turn_id] = asyncio.create_task(watchdog())

    async def send_tool_response_to_gemini(
        tool_call_id: str,
        tool_name: str,
        response: dict[str, Any],
    ) -> None:
        if gemini_connection is None:
            return
        try:
            await gemini_connection.send_tool_response(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                response=response,
            )
        except Exception:
            logger.exception("Failed sending tool response to Gemini")
            await emit(
                build_server_error_event(
                    "GEMINI_TOOL_RESPONSE_FAILED",
                    "Failed sending tool response back to Gemini Live.",
                    retryable=True,
                    session_id=state["session_id"],
                )
            )

    async def send_orchestration_context_to_gemini(
        *,
        turn_id: str,
        tool_name: str,
        tool_result: dict[str, Any],
    ) -> None:
        if gemini_connection is None:
            return
        payload = _build_orchestration_context_payload(
            tool_name=tool_name,
            tool_result=tool_result,
            turn_id=turn_id,
        )
        try:
            await gemini_connection.send_text(
                "[orchestration_context] "
                + json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
            )
        except Exception:
            logger.exception("Failed forwarding orchestration context to Gemini")
            await emit(
                build_server_error_event(
                    "GEMINI_ORCHESTRATION_CONTEXT_FAILED",
                    "Failed forwarding orchestration preflight context to Gemini Live.",
                    retryable=True,
                    session_id=state["session_id"],
                    detail={"turn_id": turn_id, "tool_name": tool_name},
                )
            )

    async def handle_gemini_function_call(function_call: Any) -> None:
        tool_call_id = getattr(function_call, "id", None) or f"tool-{uuid4().hex[:10]}"
        tool_name = getattr(function_call, "name", None) or "unknown_tool"
        raw_args = getattr(function_call, "args", None)
        args = _normalize_function_args(raw_args)
        turn_id = state["last_turn_id"]

        await emit(
            ServerToolCallEvent(
                session_id=state["session_id"] or "session-unknown",
                turn_id=turn_id,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                arguments=args,
                status="requested",
            )
        )
        try:
            result = execute_tool_call(tool_name, args)
            apply_tool_side_effects(tool_name, result)
            await emit(
                ServerToolResultEvent(
                    session_id=state["session_id"] or "session-unknown",
                    turn_id=turn_id,
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    status="completed",
                    result=result,
                )
            )
            await send_tool_response_to_gemini(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                response=result,
            )
        except ToolExecutionError as exc:
            failure_payload = {"status": "error", "message": str(exc), "tool": tool_name}
            await emit(
                ServerToolResultEvent(
                    session_id=state["session_id"] or "session-unknown",
                    turn_id=turn_id,
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    status="failed",
                    result=failure_payload,
                    error="TOOL_EXECUTION_FAILED",
                )
            )
            await send_tool_response_to_gemini(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                response=failure_payload,
            )

    async def pump_gemini_messages() -> None:
        if gemini_connection is None:
            return

        try:
            async for message in gemini_connection.receive():
                setup_complete = getattr(message, "setup_complete", None)
                if setup_complete is not None:
                    upstream_session_id = getattr(setup_complete, "session_id", None)
                    detail = "Gemini Live setup complete."
                    if upstream_session_id:
                        detail = f"{detail} upstream_session_id={upstream_session_id}"
                    await emit(
                        ServerStatusEvent(
                            phase="ready",
                            detail=detail,
                            session_id=state["session_id"],
                            resumable=True,
                        )
                    )

                server_content = getattr(message, "server_content", None)
                if server_content is not None:
                    turn_id = state["active_generation_turn_id"] or state["last_turn_id"]
                    input_transcription = getattr(server_content, "input_transcription", None)
                    if input_transcription and getattr(input_transcription, "text", None):
                        learner_text = str(input_transcription.text)
                        is_input_final = bool(getattr(input_transcription, "finished", False))
                        await emit(
                            ServerTranscriptEvent(
                                session_id=state["session_id"] or "session-unknown",
                                turn_id=turn_id,
                                speaker="learner",
                                source="input_audio",
                                text=learner_text,
                                is_final=is_input_final,
                            )
                        )
                        learner_audio_memory_buffers[turn_id] = _merge_streaming_text(
                            learner_audio_memory_buffers.get(turn_id, ""),
                            learner_text,
                        )
                        if is_input_final and not turn_buffers.get(turn_id, {}).get("texts"):
                            commit_learner_memory(turn_id, learner_audio_memory_buffers[turn_id])

                    output_transcription = getattr(server_content, "output_transcription", None)
                    if output_transcription and getattr(output_transcription, "text", None):
                        output_text = str(output_transcription.text)
                        is_output_final = bool(getattr(output_transcription, "finished", False))
                        cancel_turn_first_output_watchdog(turn_id)
                        await emit(
                            ServerTranscriptEvent(
                                session_id=state["session_id"] or "session-unknown",
                                turn_id=turn_id,
                                speaker="tutor",
                                source="output_audio_transcription",
                                text=output_text,
                                is_final=is_output_final,
                                interrupted=bool(getattr(server_content, "interrupted", False)),
                            )
                        )
                        tutor_audio_turn_ids.add(turn_id)
                        tutor_memory_buffers[turn_id] = _merge_streaming_text(
                            tutor_memory_buffers.get(turn_id, ""),
                            output_text,
                        )
                        if is_output_final:
                            flush_tutor_memory(turn_id)

                    model_turn = getattr(server_content, "model_turn", None)
                    if model_turn is not None:
                        parts = getattr(model_turn, "parts", None) or []
                        for part in parts:
                            if getattr(part, "text", None):
                                tutor_text = str(part.text)
                                is_final = bool(
                                    getattr(server_content, "generation_complete", False)
                                    or getattr(server_content, "turn_complete", False)
                                )
                                cancel_turn_first_output_watchdog(turn_id)
                                await emit(
                                    ServerTextOutputEvent(
                                        session_id=state["session_id"] or "session-unknown",
                                        turn_id=turn_id,
                                        text=tutor_text,
                                        is_final=is_final,
                                    )
                                )
                                await emit(
                                    ServerTranscriptEvent(
                                        session_id=state["session_id"] or "session-unknown",
                                        turn_id=turn_id,
                                        speaker="tutor",
                                        source="output_text",
                                        text=tutor_text,
                                        is_final=is_final,
                                        interrupted=bool(getattr(server_content, "interrupted", False)),
                                    )
                                )
                                if turn_id not in tutor_audio_turn_ids:
                                    tutor_memory_buffers[turn_id] = _merge_streaming_text(
                                        tutor_memory_buffers.get(turn_id, ""),
                                        tutor_text,
                                    )
                                    if is_final:
                                        flush_tutor_memory(turn_id)

                            inline_data = getattr(part, "inline_data", None)
                            if inline_data and getattr(inline_data, "data", None):
                                mime_type = getattr(inline_data, "mime_type", None) or OUTPUT_AUDIO_MIME_TYPE
                                if mime_type.startswith("audio/"):
                                    cancel_turn_first_output_watchdog(turn_id)
                                    chunk_index = state["audio_chunk_index"]
                                    state["audio_chunk_index"] += 1
                                    data_base64 = base64.b64encode(inline_data.data).decode("ascii")
                                    is_final_chunk = bool(
                                        getattr(server_content, "generation_complete", False)
                                        or getattr(server_content, "turn_complete", False)
                                    )
                                    await emit(
                                        ServerAudioOutputEvent(
                                            session_id=state["session_id"] or "session-unknown",
                                            turn_id=turn_id,
                                            chunk_index=chunk_index,
                                            mime_type=mime_type,
                                            data_base64=data_base64,
                                            is_final_chunk=is_final_chunk,
                                        )
                                    )
                                    await emit(
                                        ServerStatusEvent(
                                            phase="speaking",
                                            detail=f"Streaming tutor audio chunk {chunk_index}.",
                                            session_id=state["session_id"],
                                            turn_id=turn_id,
                                        )
                                    )

                    if getattr(server_content, "interrupted", False):
                        mark_turn_completed(turn_id)
                        await emit(
                            ServerTurnEvent(
                                session_id=state["session_id"] or "session-unknown",
                                turn_id=turn_id,
                                event="interrupted",
                                detail="Gemini signaled an interrupted generation.",
                            )
                        )

                    if getattr(server_content, "generation_complete", False):
                        mark_turn_completed(turn_id)
                        await emit(
                            ServerTurnEvent(
                                session_id=state["session_id"] or "session-unknown",
                                turn_id=turn_id,
                                event="generation_complete",
                                detail="Gemini generation completed for the current turn.",
                            )
                        )
                        flush_tutor_memory(turn_id)

                    if getattr(server_content, "turn_complete", False):
                        mark_turn_completed(turn_id)
                        await emit(
                            ServerTurnEvent(
                                session_id=state["session_id"] or "session-unknown",
                                turn_id=turn_id,
                                event="turn_complete",
                                detail="Gemini turn complete.",
                            )
                        )
                        flush_tutor_memory(turn_id)

                    if getattr(server_content, "waiting_for_input", False):
                        await emit(
                            ServerStatusEvent(
                                phase="listening",
                                detail="Gemini is waiting for learner input.",
                                session_id=state["session_id"],
                            )
                        )

                tool_call = getattr(message, "tool_call", None)
                if tool_call is not None:
                    function_calls = getattr(tool_call, "function_calls", None) or []
                    for function_call in function_calls:
                        await handle_gemini_function_call(function_call)

                tool_call_cancellation = getattr(message, "tool_call_cancellation", None)
                if tool_call_cancellation is not None:
                    call_ids = getattr(tool_call_cancellation, "ids", None) or []
                    if call_ids:
                        await emit(
                            ServerStatusEvent(
                                phase="tool_running",
                                detail=f"Gemini canceled tool calls: {', '.join(call_ids)}.",
                                session_id=state["session_id"],
                                turn_id=state["last_turn_id"],
                            )
                        )

                session_resumption_update = getattr(message, "session_resumption_update", None)
                if session_resumption_update is not None:
                    await emit(
                        ServerSessionUpdateEvent(
                            session_id=state["session_id"],
                            resumption_handle=getattr(session_resumption_update, "new_handle", None),
                            go_away=False,
                        )
                    )

                go_away = getattr(message, "go_away", None)
                if go_away is not None:
                    time_left_ms = _parse_duration_to_ms(getattr(go_away, "time_left", None))
                    await emit(
                        ServerSessionUpdateEvent(
                            session_id=state["session_id"],
                            go_away=True,
                            time_left_ms=time_left_ms,
                        )
                    )
                    await emit(
                        ServerStatusEvent(
                            phase="closing",
                            detail="Gemini sent a go-away signal. Prepare to reconnect or resume.",
                            session_id=state["session_id"],
                            resumable=True,
                        )
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Gemini receive loop failed")
            await emit(
                build_server_error_event(
                    "GEMINI_RECEIVE_FAILED",
                    "Gemini live receive loop failed.",
                    retryable=True,
                    session_id=state["session_id"],
                )
            )

    await emit(
        build_server_ready_event(connection_id=connection_id, websocket_path=settings.websocket_path),
    )

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break

            if message.get("bytes") is not None:
                await emit(
                    build_server_error_event(
                        "UNSUPPORTED_BINARY_FRAME",
                        "The websocket contract expects JSON frames, not raw binary frames.",
                        retryable=False,
                        session_id=state["session_id"],
                    ),
                )
                continue

            raw_text = message.get("text")
            if raw_text is None:
                continue

            try:
                raw_event = json.loads(raw_text)
            except json.JSONDecodeError:
                await emit(
                    build_server_error_event(
                        "INVALID_JSON",
                        "Incoming websocket frame was not valid JSON.",
                        retryable=False,
                        session_id=state["session_id"],
                    ),
                )
                continue

            try:
                event = parse_client_event(raw_event)
            except ValidationError as exc:
                await emit(
                    build_server_error_event(
                        "INVALID_CLIENT_EVENT",
                        "Incoming websocket event did not match the live protocol contract.",
                        retryable=False,
                        session_id=state["session_id"],
                        detail={"errors": exc.errors()},
                    ),
                )
                continue

            if isinstance(event, ClientHelloEvent):
                await close_gemini_connection()
                state["session_id"] = event.session_id or f"session-{uuid4().hex[:10]}"
                state["audio_chunk_index"] = 0
                state["last_turn_id"] = "turn-initial"
                state["active_generation_turn_id"] = None
                state["mode"] = event.mode or settings.default_tutoring_mode
                state["target_text"] = event.target_text.strip() if event.target_text else None
                state["target_reference"] = None
                state["preferred_response_language"] = (
                    event.preferred_response_language or "English"
                )
                state["pending_reference"] = None
                turn_buffers.clear()
                session_memory.clear()
                learner_audio_memory_buffers.clear()
                committed_learner_turn_ids.clear()
                tutor_memory_buffers.clear()
                tutor_audio_turn_ids.clear()
                for watchdog in turn_first_output_watchdogs.values():
                    watchdog.cancel()
                turn_first_output_watchdogs.clear()

                await emit(
                    ServerStatusEvent(
                        phase="ready",
                        detail=(
                            "Handshake accepted. Attempting Gemini Live connection for this session."
                        ),
                        session_id=state["session_id"],
                        resumable=True,
                    )
                )

                mode = event.mode or settings.default_tutoring_mode
                response_language = event.preferred_response_language or "English"
                system_prompt = build_system_prompt(
                    mode=mode,
                    response_language=response_language,
                )
                tools = tool_registry.list_definitions()

                try:
                    gemini_connection = await asyncio.wait_for(
                        gemini_gateway.connect_session(
                            system_prompt=system_prompt,
                            tools=tools,
                        ),
                        timeout=settings.gemini_connect_timeout_seconds,
                    )
                except Exception as exc:
                    logger.warning("Gemini live connect failed: %s", exc)
                    await emit(
                        build_server_error_event(
                            "GEMINI_CONNECT_FAILED",
                            (
                                "Gemini Live connection failed; continuing in scaffold mode for this "
                                "websocket session."
                            ),
                            retryable=True,
                            session_id=state["session_id"],
                            detail={"reason": str(exc)},
                        )
                    )
                    gemini_connection = None
                else:
                    gemini_receive_task = asyncio.create_task(pump_gemini_messages())
                    await emit(
                        ServerStatusEvent(
                            phase="listening",
                            detail=f"Connected to Gemini Live model {settings.gemini_live_model}.",
                            session_id=state["session_id"],
                            resumable=True,
                        )
                    )
                continue

            if state["session_id"] is None:
                await emit(
                    build_server_error_event(
                        "HELLO_REQUIRED",
                        "Send client.hello before any input events.",
                        retryable=True,
                    ),
                )
                continue

            if isinstance(event, ClientTextInputEvent):
                state["last_turn_id"] = event.turn_id
                turn_buffer = turn_buffers.setdefault(
                    event.turn_id,
                    {"texts": [], "audio_chunk_count": 0, "image_frame_count": 0},
                )
                turn_buffer["texts"].append(event.text)
                await emit(
                    ServerTranscriptEvent(
                        session_id=state["session_id"],
                        turn_id=event.turn_id,
                        speaker="learner",
                        source="input_text",
                        text=event.text,
                        is_final=event.is_final,
                    ),
                )
                if gemini_connection is None:
                    await emit(
                        ServerStatusEvent(
                            phase="receiving_input",
                            detail="Received learner text input in scaffold mode.",
                            session_id=state["session_id"],
                            turn_id=event.turn_id,
                        )
                    )
                    continue
                continue

            if isinstance(event, ClientAudioInputEvent):
                state["last_turn_id"] = event.turn_id
                turn_buffer = turn_buffers.setdefault(
                    event.turn_id,
                    {"texts": [], "audio_chunk_count": 0, "image_frame_count": 0},
                )
                turn_buffer["audio_chunk_count"] += 1
                if gemini_connection is None:
                    await emit(
                        ServerStatusEvent(
                            phase="receiving_input",
                            detail=f"Received audio chunk {event.chunk_index} in scaffold mode.",
                            session_id=state["session_id"],
                            turn_id=event.turn_id,
                        )
                    )
                    continue
                try:
                    audio_bytes = _decode_base64_payload(
                        event.data_base64,
                        field_name="client.input.audio.data_base64",
                    )
                except ValueError as exc:
                    await emit(
                        build_server_error_event(
                            "INVALID_AUDIO_BASE64",
                            str(exc),
                            retryable=False,
                            session_id=state["session_id"],
                            detail={"turn_id": event.turn_id, "chunk_index": event.chunk_index},
                        )
                    )
                    continue
                try:
                    await gemini_connection.send_audio_chunk(
                        audio_bytes=audio_bytes,
                        mime_type=event.mime_type,
                        is_final_chunk=event.is_final_chunk,
                    )
                except Exception:
                    logger.exception("Failed forwarding audio input to Gemini")
                    await emit(
                        build_server_error_event(
                            "GEMINI_SEND_AUDIO_FAILED",
                            "Failed forwarding learner audio to Gemini Live.",
                            retryable=True,
                            session_id=state["session_id"],
                            detail={"turn_id": event.turn_id, "chunk_index": event.chunk_index},
                        )
                    )
                continue

            if isinstance(event, ClientImageInputEvent):
                state["last_turn_id"] = event.turn_id
                turn_buffer = turn_buffers.setdefault(
                    event.turn_id,
                    {"texts": [], "audio_chunk_count": 0, "image_frame_count": 0},
                )
                turn_buffer["image_frame_count"] += 1
                if gemini_connection is None:
                    await emit(
                        ServerStatusEvent(
                            phase="receiving_input",
                            detail=(
                                f"Received {event.source} frame {event.frame_index} in scaffold mode."
                            ),
                            session_id=state["session_id"],
                            turn_id=event.turn_id,
                        )
                    )
                    continue
                try:
                    image_bytes = _decode_base64_payload(
                        event.data_base64,
                        field_name="client.input.image.data_base64",
                    )
                except ValueError as exc:
                    await emit(
                        build_server_error_event(
                            "INVALID_IMAGE_BASE64",
                            str(exc),
                            retryable=False,
                            session_id=state["session_id"],
                            detail={"turn_id": event.turn_id, "frame_index": event.frame_index},
                        )
                    )
                    continue
                try:
                    await gemini_connection.send_image_chunk(
                        image_bytes=image_bytes,
                        mime_type=event.mime_type,
                    )
                except Exception:
                    logger.exception("Failed forwarding image input to Gemini")
                    await emit(
                        build_server_error_event(
                            "GEMINI_SEND_IMAGE_FAILED",
                            "Failed forwarding image input to Gemini Live.",
                            retryable=True,
                            session_id=state["session_id"],
                            detail={"turn_id": event.turn_id, "frame_index": event.frame_index},
                        )
                    )
                continue

            if isinstance(event, ClientTurnEndEvent):
                active_turn_id = state["active_generation_turn_id"]
                if active_turn_id and active_turn_id != event.turn_id:
                    # Recover from stale in-flight turns so a new learner turn can proceed
                    # without leaving the UI stuck in a thinking state.
                    if gemini_connection is not None and hasattr(gemini_connection, "interrupt"):
                        try:
                            await gemini_connection.interrupt()
                        except Exception:
                            logger.exception("Failed interrupting stale Gemini turn")
                    mark_turn_completed(active_turn_id)
                    flush_tutor_memory(active_turn_id)
                state["last_turn_id"] = event.turn_id
                turn_buffer = turn_buffers.pop(
                    event.turn_id,
                    {"texts": [], "audio_chunk_count": 0, "image_frame_count": 0},
                )
                learner_turn_text = "\n".join(turn_buffer["texts"]).strip()
                if not learner_turn_text:
                    learner_turn_text = learner_audio_memory_buffers.get(event.turn_id, "")
                turn_input = LiveTurnInput(
                    turn_id=event.turn_id,
                    reason=event.reason,
                    learner_text=learner_turn_text,
                    audio_chunk_count=int(turn_buffer["audio_chunk_count"]),
                    image_frame_count=int(turn_buffer["image_frame_count"]),
                )
                if turn_input.learner_text:
                    commit_learner_memory(event.turn_id, turn_input.learner_text)

                learner_text = turn_input.learner_text
                if learner_text and looks_like_reference_request(learner_text) and not state["target_text"]:
                    state["pending_reference"] = _compact_text(learner_text)

                if learner_text and _is_read_request(learner_text) and state["pending_reference"] and not state["target_text"]:
                    await emit(
                        ServerTurnEvent(
                            session_id=state["session_id"],
                            turn_id=event.turn_id,
                            event="learner_turn_closed",
                            detail=f"Learner turn ended because: {event.reason}.",
                        )
                    )
                    await emit_local_tutor_reply(
                        event.turn_id,
                        (
                            f"I still do not have the text of {state['pending_reference']} in the session. "
                            "Paste the verse or point your camera at it, and then I can read it with you."
                        ),
                    )
                    continue

                if learner_text and state["target_text"]:
                    state["pending_reference"] = None
                plan = await turn_orchestrator.plan_turn(
                    mode=state["mode"],
                    target_text=state["target_text"],
                    preferred_response_language=state["preferred_response_language"],
                    turn_input=turn_input,
                )

                await emit(
                    ServerTurnEvent(
                        session_id=state["session_id"],
                        turn_id=event.turn_id,
                        event="learner_turn_closed",
                        detail=f"Learner turn ended because: {event.reason}.",
                    )
                )
                await emit(
                    ServerStatusEvent(
                        phase="tool_running" if plan.preflight_tool_name else "thinking",
                        detail=f"Turn orchestration ({plan.engine}): {plan.rationale}",
                        session_id=state["session_id"],
                        turn_id=event.turn_id,
                    )
                )

                if plan.preflight_tool_name is not None:
                    normalized_preflight_arguments = _normalize_preflight_tool_arguments(
                        plan.preflight_tool_name,
                        plan.preflight_tool_arguments,
                        learner_text=learner_text,
                        target_text=state["target_text"],
                        preferred_response_language=state["preferred_response_language"],
                        mode=state["mode"],
                    )
                    orchestrator_tool_call_id = f"orch-{event.turn_id}-{uuid4().hex[:8]}"
                    await emit(
                        ServerToolCallEvent(
                            session_id=state["session_id"],
                            turn_id=event.turn_id,
                            tool_call_id=orchestrator_tool_call_id,
                            tool_name=plan.preflight_tool_name,
                            arguments=normalized_preflight_arguments,
                            status="started",
                        )
                    )
                    try:
                        preflight_result = execute_tool_call(
                            plan.preflight_tool_name,
                            normalized_preflight_arguments,
                        )
                    except ToolExecutionError as exc:
                        failure_payload = {"status": "error", "message": str(exc)}
                        await emit(
                            ServerToolResultEvent(
                                session_id=state["session_id"],
                                turn_id=event.turn_id,
                                tool_call_id=orchestrator_tool_call_id,
                                tool_name=plan.preflight_tool_name,
                                status="failed",
                                result=failure_payload,
                                error="ORCHESTRATION_PREFLIGHT_FAILED",
                            )
                        )
                        if (
                            plan.preflight_tool_name == "resolve_reference"
                            and state["pending_reference"]
                            and not state["target_text"]
                        ):
                            failure_message = str(failure_payload.get("message", "")).strip()
                            await emit_local_tutor_reply(
                                event.turn_id,
                                failure_message
                                or (
                                    f"I could not resolve {state['pending_reference']} from the current corpus. "
                                    "Paste the Greek text or show it on camera, and I can work with it directly."
                                ),
                            )
                            continue
                        await send_orchestration_context_to_gemini(
                            turn_id=event.turn_id,
                            tool_name=plan.preflight_tool_name,
                            tool_result={
                                **failure_payload,
                                "orchestration_engine": plan.engine,
                                "orchestration_stage": plan.stage,
                            },
                        )
                    else:
                        apply_tool_side_effects(plan.preflight_tool_name, preflight_result)
                        preflight_result_with_meta = {
                            **preflight_result,
                            "orchestration_engine": plan.engine,
                            "orchestration_stage": plan.stage,
                        }
                        await emit(
                            ServerToolResultEvent(
                                session_id=state["session_id"],
                                turn_id=event.turn_id,
                                tool_call_id=orchestrator_tool_call_id,
                                tool_name=plan.preflight_tool_name,
                                status="completed",
                                result=preflight_result_with_meta,
                            )
                        )
                        if (
                            plan.preflight_tool_name == "resolve_reference"
                            and preflight_result.get("status") != "ok"
                            and state["pending_reference"]
                            and not state["target_text"]
                        ):
                            failure_message = str(preflight_result.get("message", "")).strip()
                            await emit_local_tutor_reply(
                                event.turn_id,
                                failure_message
                                or (
                                    f"I could not resolve {state['pending_reference']} from the current corpus. "
                                    "Paste the Greek text or show it on camera, and I can work with it directly."
                                ),
                            )
                            continue
                        if (
                            plan.preflight_tool_name == "resolve_reference"
                            and preflight_result.get("status") == "ok"
                            and learner_text
                            and looks_like_reference_request(learner_text)
                        ):
                            resolved_reference = str(
                                preflight_result.get("reference")
                                or preflight_result.get("normalized_reference")
                                or state["target_reference"]
                                or learner_text
                            ).strip()
                            await emit_local_tutor_reply(
                                event.turn_id,
                                (
                                    f"I've loaded {resolved_reference}. "
                                    "Would you like me to read it aloud, parse the first clause, or give a translation hint?"
                                ),
                            )
                            continue
                        await send_orchestration_context_to_gemini(
                            turn_id=event.turn_id,
                            tool_name=plan.preflight_tool_name,
                            tool_result=preflight_result_with_meta,
                        )

                if gemini_connection is not None and turn_input.learner_text:
                    mode_value = (
                        state["mode"].value
                        if hasattr(state["mode"], "value")
                        else str(state["mode"])
                    )
                    learner_payload = _build_session_context_message(
                        history=list(session_memory),
                        mode=mode_value,
                        target_reference=state["target_reference"],
                        target_text=state["target_text"],
                        preferred_response_language=state["preferred_response_language"],
                    )
                    try:
                        await gemini_connection.send_text(learner_payload)
                    except Exception:
                        logger.exception("Failed forwarding learner turn text to Gemini")
                        await emit(
                            build_server_error_event(
                                "GEMINI_SEND_TEXT_FAILED",
                                "Failed forwarding learner text to Gemini Live.",
                                retryable=True,
                                session_id=state["session_id"],
                                detail={"turn_id": event.turn_id},
                            )
                        )

                await emit(
                    ServerStatusEvent(
                        phase="thinking",
                        detail="Learner turn closed. Awaiting tutor generation.",
                        session_id=state["session_id"],
                        turn_id=event.turn_id,
                    )
                )
                if gemini_connection is not None:
                    state["active_generation_turn_id"] = event.turn_id
                    try:
                        if turn_input.audio_chunk_count > 0 and hasattr(gemini_connection, "end_audio_stream"):
                            await gemini_connection.end_audio_stream()
                        await gemini_connection.end_turn()
                        arm_turn_first_output_watchdog(event.turn_id)
                    except Exception:
                        mark_turn_completed(event.turn_id)
                        logger.exception("Failed signaling turn end to Gemini")
                        await emit(
                            build_server_error_event(
                                "GEMINI_TURN_END_FAILED",
                                "Failed signaling learner turn end to Gemini Live.",
                                retryable=True,
                                session_id=state["session_id"],
                                detail={"turn_id": event.turn_id},
                            )
                        )
                else:
                    mark_turn_completed(event.turn_id)
                continue

            if isinstance(event, ClientInterruptEvent):
                interrupt_turn_id = (
                    event.turn_id
                    or state["active_generation_turn_id"]
                    or state["last_turn_id"]
                )
                mark_turn_completed(interrupt_turn_id)
                await emit(
                    ServerStatusEvent(
                        phase="interrupted",
                        detail=f"Interrupt received from the client: {event.reason}.",
                        session_id=state["session_id"],
                        turn_id=event.turn_id,
                    )
                )
                await emit(
                    ServerTurnEvent(
                        session_id=state["session_id"],
                        turn_id=interrupt_turn_id,
                        event="interrupted",
                        detail="Client requested that current playback or generation stop.",
                    )
                )
                if gemini_connection is not None:
                    try:
                        if hasattr(gemini_connection, "interrupt"):
                            await gemini_connection.interrupt()
                        else:
                            await gemini_connection.end_turn()
                    except Exception:
                        logger.exception("Failed forwarding interrupt to Gemini")
                        await emit(
                            build_server_error_event(
                                "GEMINI_INTERRUPT_FAILED",
                                "Failed forwarding interrupt signal to Gemini Live.",
                                retryable=True,
                                session_id=state["session_id"],
                            )
                        )
                continue

            if isinstance(event, ClientPingEvent):
                await emit(
                    ServerStatusEvent(
                        phase="listening",
                        detail="pong",
                        session_id=state["session_id"],
                    )
                )
    except WebSocketDisconnect:
        return
    finally:
        await close_gemini_connection()

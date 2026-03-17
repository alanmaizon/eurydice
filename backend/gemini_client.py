"""
Gemini Live API integration for Logos.

SDK: google-genai >= 1.67.0
Docs: https://pypi.org/project/google-genai/

Auth modes:
  Vertex AI   — genai.Client(vertexai=True, project=..., location=...)
                Uses Application Default Credentials (ADC).
                Enable by setting GCP_PROJECT_ID.
  AI Studio   — genai.Client(api_key=...)
                Enable by setting GEMINI_API_KEY.

Session methods used (non-deprecated):
  session.send_client_content()  — turn-based text / inline images
  session.send_realtime_input()  — real-time audio or video blobs
                                   ONE named parameter per call (audio, video, or text)
                                   Do NOT interleave with send_client_content
  session.send_tool_response()   — return function-call results to the model
"""

import asyncio
import base64
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Gemini Live audio-transcription can emit internal control tokens like <ctrl46>
# alongside genuine non-printable characters. Strip both before forwarding text.
_CTRL_TOKEN_RE = re.compile(r'<ctrl\d+>', re.IGNORECASE)
_CTRL_CHAR_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\ufeff]')
# Matches: GreekToken (single-word Latin/accented ≤30 chars) — strips transliterations.
# Preserves multi-word parentheticals (εἰμί (to be)) and prose parens (Peter (not Paul)).
_TRANSLIT_PARENS_RE = re.compile(
    r'([^\s]*[\u0370-\u03ff\u1f00-\u1fff][^\s]*)\s*\([A-Za-z\u00c0-\u024f\'-]{1,30}\)',
)


def _sanitize_transcript(raw: str) -> str:
    """Remove control tokens, non-printable chars, and parenthetical transliterations."""
    cleaned = _CTRL_TOKEN_RE.sub('', raw)
    cleaned = _CTRL_CHAR_RE.sub('', cleaned)
    cleaned = _TRANSLIT_PARENS_RE.sub(r'\1', cleaned)
    if cleaned != raw:
        logger.debug("transcript sanitized — raw=%r → cleaned=%r", raw[:120], cleaned[:120])
    return cleaned


# ── Spoken-safe tool result ────────────────────────────────────────────────────
# Fields that belong in the UI card but must NOT be fed back to the live model.
# The model narrates whatever it receives in send_tool_response; removing these
# fields from the model-facing payload prevents them from being spoken aloud.
# The full result is still forwarded to the frontend via ToolResultMessage so
# ParseCard / LexiconCard / ScansionCard render with complete data.
# Internal debug fields produced by meter.py — never needed in the UI card.
_INTERNAL_RESULT_FIELDS = frozenset({"_timing_ms", "_timing_detail", "_method", "_note"})

_VISUAL_ONLY_FIELDS: dict[str, frozenset] = {
    "parse_greek":    frozenset({"transliteration", "ipa", "principal_parts"}),
    "lookup_lexicon": frozenset({"transliteration", "principal_parts", "key_refs"}),
    # pattern is visual (— ∪∪ | notation); analysis can be a complex foot-by-foot
    # array that the model would otherwise narrate verbatim — strip both.
    "scan_meter":     frozenset({"pattern", "analysis"}),
}


def _make_spoken_safe(tool_name: str, result: Any) -> Any:
    """Return *result* with visual-only fields removed.

    The model uses this dict to compose its verbal summary; stripping
    transliteration, IPA, principal parts, and scansion patterns ensures the
    model cannot narrate them even if it ignores the system-prompt rules.
    The caller is responsible for sending the full result to the frontend.
    """
    if not isinstance(result, dict):
        return result
    drop = _VISUAL_ONLY_FIELDS.get(tool_name, frozenset())
    return {k: v for k, v in result.items() if k not in drop}

from config import settings, USE_VERTEX_AI
from models import (
    SessionStartedMessage,
    SessionEndedMessage,
    StatusMessage,
    TextDeltaMessage,
    TextDoneMessage,
    AudioDeltaMessage,
    AudioDoneMessage,
    ToolCallMessage,
    ToolResultMessage,
    ErrorMessage,
    LogMessage,
)
from tools import TOOL_DECLARATIONS, execute_tool_live
from audio import pcm_to_base64


def _build_client() -> Any:
    """Return a google-genai Client for Vertex AI or AI Studio."""
    from google import genai  # type: ignore[import]

    if USE_VERTEX_AI:
        return genai.Client(
            vertexai=True,
            project=settings.gcp_project_id,
            location=settings.gcp_region,
        )
    return genai.Client(api_key=settings.gemini_api_key)


async def run_gemini_session(
    websocket: Any,
    config: dict[str, Any],
) -> None:
    from google.genai import types  # type: ignore[import]

    client = _build_client()
    system_instruction = config.get("system_instruction", "")
    session_id = f"live-{uuid.uuid4().hex[:8]}"

    async def send(msg: Any) -> None:
        if hasattr(msg, "model_dump"):
            await websocket.send_text(json.dumps(msg.model_dump()))
        else:
            await websocket.send_text(json.dumps(msg))

    def now() -> str:
        return datetime.now(timezone.utc).isoformat()

    # ── LiveConnectConfig ────────────────────────────────────────────────────
    # Tools passed as raw dicts — avoids having to construct Schema objects
    # manually and is fully supported by the SDK.
    live_config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=(
            types.Content(parts=[types.Part(text=system_instruction)])
            if system_instruction
            else None
        ),
        tools=[{"function_declarations": TOOL_DECLARATIONS}],
        output_audio_transcription=types.AudioTranscriptionConfig(),
        input_audio_transcription=types.AudioTranscriptionConfig(),
    )

    await send(StatusMessage(state="connecting"))

    try:
        async with client.aio.live.connect(
            model=settings.gemini_model,
            config=live_config,
        ) as session:
            await send(SessionStartedMessage(session_id=session_id))
            await send(StatusMessage(state="live"))
            await send(LogMessage(
                event="session.started",
                data={"session_id": session_id, "vertex_ai": USE_VERTEX_AI},
                timestamp=now(),
            ))

            # True when the session is using send_realtime_input (audio mode).
            # False when using send_client_content (text / image mode).
            # We track this to avoid the SDK's interleaving restriction.
            _in_realtime_mode = False
            input_queue: asyncio.Queue[Optional[dict[str, Any]]] = asyncio.Queue()

            async def receive_from_client() -> None:
                while True:
                    try:
                        raw = await websocket.receive_text()
                        await input_queue.put(json.loads(raw))
                    except Exception:
                        await input_queue.put(None)
                        break

            async def send_to_gemini() -> None:
                nonlocal _in_realtime_mode
                while True:
                    msg = await input_queue.get()
                    if msg is None:
                        break

                    msg_type: Optional[str] = msg.get("type")

                    if msg_type == "session.end":
                        await input_queue.put(None)
                        break

                    elif msg_type == "input.text":
                        # SDK 1.67+ requires types.Content, not a bare string.
                        _in_realtime_mode = False
                        await session.send_client_content(
                            turns=types.Content(
                                role="user",
                                parts=[types.Part(text=msg["text"])],
                            ),
                            turn_complete=True,
                        )

                    elif msg_type == "input.audio":
                        # Real-time audio — use send_realtime_input with
                        # the `audio` named parameter (ONE param per call).
                        _in_realtime_mode = True
                        pcm_data = base64.b64decode(msg["audio"])
                        await session.send_realtime_input(
                            audio=types.Blob(
                                data=pcm_data,
                                mime_type="audio/pcm;rate=16000",
                            )
                        )

                    elif msg_type == "input.image":
                        # Images are turn-based — bundle image + instruction
                        # in a single send_client_content call to avoid the
                        # interleaving restriction.
                        _in_realtime_mode = False
                        image_data = base64.b64decode(msg["image"])
                        mime = msg.get("mime_type", "image/jpeg")
                        content = types.Content(
                            role="user",
                            parts=[
                                types.Part(
                                    inline_data=types.Blob(
                                        data=image_data, mime_type=mime
                                    )
                                ),
                                types.Part(
                                    text=(
                                        "Please describe, transcribe, and analyze "
                                        "this image in the context of Ancient Greek "
                                        "scholarship."
                                    )
                                ),
                            ],
                        )
                        await session.send_client_content(
                            turns=content,
                            turn_complete=True,
                        )

                    elif msg_type == "input.interrupt":
                        # Force a new empty turn — this preempts whatever the model
                        # is currently generating, giving a "barge-in" effect.
                        await session.send_client_content(turns=[], turn_complete=True)
                        await send(LogMessage(event="input.interrupt", timestamp=now()))

                    if msg_type:
                        await send(LogMessage(event=msg_type, timestamp=now()))

            async def receive_from_gemini() -> None:
                # session.receive() yields exactly ONE model turn then stops —
                # the SDK breaks internally after turn_complete (confirmed by
                # reading the source). Re-enter it after each turn so the
                # coroutine keeps running for the full multi-turn session.
                current_text = ""
                while True:
                    try:
                        async for response in session.receive():
                            # ── Diagnostic: emit raw event type to inspector ─────
                            if getattr(response, "setup_complete", None):
                                await send(LogMessage(event="gemini.setup_complete", timestamp=now()))
                                continue  # Nothing to forward; session is ready

                            if getattr(response, "server_content", None) is not None:
                                evt = "gemini.server_content"
                            elif getattr(response, "tool_call", None) is not None:
                                evt = "gemini.tool_call"
                            else:
                                evt = "gemini.unknown"
                            await send(LogMessage(event=evt, timestamp=now()))

                            # ── server_content: audio parts + transcription ───────
                            server_content = getattr(response, "server_content", None)
                            if server_content is not None:
                                model_turn = getattr(server_content, "model_turn", None)
                                if model_turn is not None:
                                    for part in (getattr(model_turn, "parts", None) or []):
                                        inline = getattr(part, "inline_data", None)
                                        if inline is not None:
                                            data = getattr(inline, "data", None)
                                            if data:
                                                await send(AudioDeltaMessage(audio=pcm_to_base64(data)))

                                out_tx = getattr(server_content, "output_transcription", None)
                                if out_tx is not None:
                                    tx_text = getattr(out_tx, "text", None)
                                    if tx_text:
                                        tx_text = _sanitize_transcript(tx_text)
                                        if tx_text:  # may be empty after stripping
                                            await send(TextDeltaMessage(delta=tx_text))
                                            current_text += tx_text

                                if getattr(server_content, "turn_complete", False):
                                    if current_text:
                                        await send(TextDoneMessage(full_text=current_text))
                                        current_text = ""
                                    await send(AudioDoneMessage())

                            # ── Tool / function call ─────────────────────────────
                            tool_call = getattr(response, "tool_call", None)
                            if tool_call is not None:
                                for fc in (getattr(tool_call, "function_calls", None) or []):
                                    call_id: str = getattr(fc, "id", None) or f"call-{uuid.uuid4().hex[:8]}"
                                    args: dict[str, Any] = dict(fc.args) if getattr(fc, "args", None) else {}

                                    await send(ToolCallMessage(
                                        tool_name=fc.name,
                                        args=args,
                                        call_id=call_id,
                                    ))

                                    result = await execute_tool_live(fc.name, args, client)

                                    # Strip internal debug fields (timing, method) before
                                    # forwarding to the frontend — they're noise in the UI.
                                    frontend_result = (
                                        {k: v for k, v in result.items() if k not in _INTERNAL_RESULT_FIELDS}
                                        if isinstance(result, dict) else result
                                    )

                                    # Full result → frontend (ParseCard / LexiconCard get all fields)
                                    await send(ToolResultMessage(call_id=call_id, result=frontend_result))
                                    await send(LogMessage(
                                        event="tool.executed",
                                        data={"tool": fc.name, "call_id": call_id},
                                        timestamp=now(),
                                    ))

                                    # Spoken-safe result → model (strips transliteration, IPA,
                                    # principal parts, etc. so the model cannot narrate them)
                                    spoken_result = _make_spoken_safe(fc.name, result)
                                    await session.send_tool_response(
                                        function_responses=types.FunctionResponse(
                                            name=fc.name,
                                            id=call_id,
                                            response={"output": spoken_result},
                                        )
                                    )
                    except Exception as exc:
                        import traceback as tb
                        tb.print_exception(type(exc), exc, exc.__traceback__)
                        await send(LogMessage(
                            event="recv.error",
                            data={"error": str(exc)},
                            timestamp=now(),
                        ))
                        break

            client_task = asyncio.create_task(receive_from_client())
            send_task = asyncio.create_task(send_to_gemini())
            recv_task = asyncio.create_task(receive_from_gemini())

            results = await asyncio.gather(
                client_task, send_task, recv_task, return_exceptions=True
            )
            for res in results:
                if isinstance(res, Exception):
                    import traceback as tb
                    tb.print_exception(type(res), res, res.__traceback__)
                    await send(LogMessage(
                        event="task.error",
                        data={"error": str(res)},
                        timestamp=now(),
                    ))

    except Exception as exc:
        await send(ErrorMessage(message=str(exc), code="GEMINI_ERROR"))
        await send(StatusMessage(state="error"))
    finally:
        await send(SessionEndedMessage())
        await send(StatusMessage(state="ended"))
        await send(LogMessage(event="session.ended", timestamp=now()))

"""
Claude (Anthropic) Messages API integration for Eurydice.

Uses the Anthropic Python SDK with async streaming and tool use.
Claude acts as the teaching/orchestration layer; audio_analysis and
vision_analysis tools produce measurements that Claude interprets into coaching.

Session protocol matches gemini_client.py — same WebSocket message types.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from config import settings
from eurydice_session import (
    SessionState,
    EurydiceSession,
    create_session,
    drop_session,
)
from models import (
    SessionStartedMessage,
    SessionEndedMessage,
    StatusMessage,
    TextDeltaMessage,
    TextDoneMessage,
    ToolCallMessage,
    ToolResultMessage,
    ErrorMessage,
    LogMessage,
    StateChangedMessage,
    MasteryUpdateMessage,
    MasteryAchievedMessage,
)
from config import USE_MOCK
from tools import (
    EURYDICE_TOOL_DECLARATIONS,
    execute_eurydice_tool_mock,
    execute_eurydice_tool_live,
)

logger = logging.getLogger(__name__)

# Anthropic tool format uses input_schema; convert from the shared declaration format
def _to_anthropic_tools(declarations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": t["name"],
            "description": t["description"],
            "input_schema": t["parameters"],
        }
        for t in declarations
    ]

ANTHROPIC_TOOLS = _to_anthropic_tools(EURYDICE_TOOL_DECLARATIONS)


async def run_claude_session(websocket: Any, config: dict[str, Any]) -> None:
    """
    Top-level Claude session handler.

    Maintains conversation history and drives the tool-use loop:
      1. Stream Claude's response, forwarding text deltas to the client.
      2. If Claude requests tool calls, execute them and feed results back.
      3. Continue until Claude's stop_reason is "end_turn".
    """
    from anthropic import AsyncAnthropic

    session_id = f"claude-{uuid.uuid4().hex[:8]}"
    system_instruction = config.get("system_instruction", "")
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    # Session state machine
    sess: EurydiceSession = create_session(session_id)

    # Conversation history (stateful across turns in this session)
    messages: list[dict[str, Any]] = []

    async def send(msg: Any) -> None:
        payload = msg.model_dump() if hasattr(msg, "model_dump") else msg
        await websocket.send_text(json.dumps(payload))

    def now() -> str:
        return datetime.now(timezone.utc).isoformat()

    async def emit_state(previous: SessionState | None = None) -> None:
        await send(StateChangedMessage(
            state=sess.state.value,
            previous=previous.value if previous else None,
        ))

    # ── Handshake ─────────────────────────────────────────────────────────────
    await send(StatusMessage(state="connecting"))
    await send(SessionStartedMessage(session_id=session_id))
    await send(StatusMessage(state="live"))
    await emit_state()
    await send(LogMessage(
        event="session.started",
        data={"session_id": session_id},
        timestamp=now(),
    ))

    # ── Per-turn tool-use loop ─────────────────────────────────────────────────

    async def handle_turn(
        user_content: list[dict[str, Any]],
        system_override: str | None = None,
    ) -> None:
        """
        Append a user turn and run the Claude agentic loop until end_turn.
        Streams text deltas to the client and executes any tool calls.
        system_override replaces the base system instruction for this turn (carries session context).
        """
        messages.append({"role": "user", "content": user_content})

        while True:
            full_text = ""
            effective_system = system_override or system_instruction or None

            # Stream this Claude call
            async with client.messages.stream(
                model="claude-opus-4-6",
                max_tokens=4096,
                system=effective_system,
                messages=messages,
                tools=ANTHROPIC_TOOLS,
                thinking={"type": "adaptive"},
            ) as stream:
                async for text in stream.text_stream:
                    full_text += text
                    await send(TextDeltaMessage(delta=text))

                final = await stream.get_final_message()

            # Emit text.done
            if full_text:
                await send(TextDoneMessage(full_text=full_text))

            # Build assistant content list and collect tool_use blocks
            assistant_content: list[dict[str, Any]] = []
            tool_uses: list[dict[str, Any]] = []

            for block in final.content:
                if block.type == "thinking":
                    # Preserve thinking signature for multi-turn correctness
                    assistant_content.append({
                        "type": "thinking",
                        "thinking": block.thinking,
                        "signature": block.signature,
                    })
                elif block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    tool_uses.append({
                        "id": block.id,
                        "name": block.name,
                        "input": dict(block.input),
                    })
                    assistant_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": dict(block.input),
                    })

            messages.append({"role": "assistant", "content": assistant_content})

            # No tools called → done with this turn
            if not tool_uses:
                break

            # Execute tools and gather results
            tool_results: list[dict[str, Any]] = []
            for tu in tool_uses:
                call_id: str = tu["id"]
                tool_name: str = tu["name"]
                args: dict[str, Any] = tu["input"]

                # Inject target context into audio_analysis args
                if tool_name == "audio_analysis":
                    if sess.target.target_bpm and "target_bpm" not in args:
                        args["target_bpm"] = sess.target.target_bpm
                    if sess.target.target_notes and "target_notes" not in args:
                        args["target_notes"] = sess.target.target_notes
                    prev_state = sess.state
                    mode = args.get("mode", "quick")
                    sess.transition(
                        SessionState.PROCESSING_DEEP if mode == "deep"
                        else SessionState.PROCESSING_QUICK
                    )
                    await emit_state(prev_state)

                await send(ToolCallMessage(tool_name=tool_name, args=args, call_id=call_id))
                await send(LogMessage(
                    event="tool.call",
                    data={"tool": tool_name, "call_id": call_id},
                    timestamp=now(),
                ))

                result = (
                    execute_eurydice_tool_mock(tool_name, args)
                    if USE_MOCK
                    else execute_eurydice_tool_live(tool_name, args)
                )

                # Post-process audio_analysis: run mastery gate + emit updates
                if tool_name == "audio_analysis" and "performance_scores" in result:
                    mastery_check = sess.record_attempt(result)
                    result["_mastery"] = mastery_check.to_dict()

                    await send(MasteryUpdateMessage(
                        consecutive_passes=mastery_check.consecutive_passes,
                        passes_needed=mastery_check.passes_needed,
                        mastered=mastery_check.mastered,
                        gate_detail=mastery_check.gate_detail,
                        attempt_number=mastery_check.attempt.attempt_number,
                    ))

                    if mastery_check.mastered:
                        await send(MasteryAchievedMessage(
                            total_attempts=len(sess.mastery_gate.attempts),
                            passage_description=sess.target.description or None,
                        ))
                        await emit_state()
                    else:
                        prev_state = sess.state
                        sess.transition(
                            SessionState.FEEDBACK_DEEP if mode == "deep"
                            else SessionState.FEEDBACK_QUICK
                        )
                        await emit_state(prev_state)

                await send(ToolResultMessage(call_id=call_id, result=result))
                await send(LogMessage(
                    event="tool.executed",
                    data={"tool": tool_name, "call_id": call_id},
                    timestamp=now(),
                ))

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": call_id,
                    "content": json.dumps(result),
                })

            # Feed results back to Claude
            messages.append({"role": "user", "content": tool_results})

    def _system_with_context() -> str | None:
        """Append current session state to the system prompt so Claude always has it."""
        ctx = sess.to_context_dict()
        state_block = (
            f"\n\n---\nCurrent session state: {ctx['state']}\n"
            f"Target: {ctx['target']['description'] or '(not set)'}"
            + (f" @ {ctx['target']['target_bpm']} BPM" if ctx['target']['target_bpm'] else "")
            + f"\nMastery: {ctx['mastery']['consecutive_passes']}/{ctx['mastery']['thresholds']['consecutive_required']} consecutive passes"
            + (f" — MASTERED" if ctx['mastery']['mastered'] else f", {ctx['mastery']['passes_needed']} more needed")
            + "\n---"
        )
        return (system_instruction + state_block) if system_instruction else state_block.strip()

    # ── Main session receive loop ──────────────────────────────────────────────
    try:
        while True:
            try:
                raw = await websocket.receive_text()
                msg = json.loads(raw)
            except Exception:
                break

            msg_type: str | None = msg.get("type")
            if msg_type:
                await send(LogMessage(event=msg_type, timestamp=now()))

            if msg_type == "session.end":
                break

            elif msg_type == "target.set":
                prev = sess.state
                sess.set_target(
                    description=msg.get("description", ""),
                    target_bpm=msg.get("target_bpm"),
                    target_notes=msg.get("target_notes"),
                    difficulty=msg.get("difficulty", "beginner"),
                )
                await emit_state(prev)
                # Acknowledge to Claude so it can greet the user with the target
                user_content = [{
                    "type": "text",
                    "text": (
                        f"Target passage set: {msg.get('description', '(unnamed)')}"
                        + (f" at {msg.get('target_bpm')} BPM" if msg.get('target_bpm') else "")
                        + f". Difficulty: {msg.get('difficulty', 'beginner')}."
                        " Acknowledge the target and tell the user to record a take when ready."
                    ),
                }]
                await handle_turn(user_content, _system_with_context())

            elif msg_type == "input.text":
                user_content = [{"type": "text", "text": msg["text"]}]
                await handle_turn(user_content, _system_with_context())

            elif msg_type == "input.audio_recording":
                # Full WAV buffer from the recording button — trigger audio analysis
                audio_b64: str = msg["audio_b64"]
                duration_s: float | None = msg.get("duration_s")
                prev = sess.state
                sess.transition(SessionState.RECORDING)
                await emit_state(prev)
                user_content = [{
                    "type": "text",
                    "text": (
                        f"The user just recorded a guitar take"
                        + (f" ({duration_s:.1f}s)" if duration_s else "")
                        + ". The audio is attached as base64 WAV in the audio_b64 field below. "
                        "Call audio_analysis with mode='quick' and this audio_b64 to score the take."
                        f"\naudio_b64: {audio_b64[:40]}... (truncated for display)"
                    ),
                }]
                # Pass the actual audio_b64 via a separate content block so the model can forward it
                # to the tool — we attach it as a structured hint rather than raw text
                user_content.append({
                    "type": "text",
                    "text": f"__AUDIO_B64__:{audio_b64}",
                })
                await handle_turn(user_content, _system_with_context())

            elif msg_type == "input.image":
                image_b64: str = msg["image"]
                mime: str = msg.get("mime_type", "image/jpeg")
                user_content = [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime,
                            "data": image_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "Please analyze this guitar technique image using "
                            "vision_analysis and provide actionable feedback."
                        ),
                    },
                ]
                await handle_turn(user_content, _system_with_context())

            elif msg_type == "input.interrupt":
                await send(LogMessage(event="input.interrupt", timestamp=now()))

    except Exception as exc:
        logger.exception("Claude session error")
        sess.force_state(SessionState.ERROR)
        try:
            await send(ErrorMessage(message=str(exc), code="CLAUDE_ERROR"))
            await send(StatusMessage(state="error"))
        except Exception:
            pass
    finally:
        drop_session(session_id)
        await send(SessionEndedMessage())
        await send(StatusMessage(state="ended"))
        await send(LogMessage(event="session.ended", timestamp=now()))

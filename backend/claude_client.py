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
import time
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
    TargetValidationMessage,
    CaptureInvalidMessage,
)
from config import USE_MOCK
from telemetry import get_collector
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


_TARGET_PARSE_SYSTEM = (
    "You extract structured fields from a guitar practice target description. "
    "Return JSON with these optional fields:\n"
    '  "clean_description": the passage description without BPM/difficulty mentions,\n'
    '  "bpm": integer BPM if mentioned (null otherwise),\n'
    '  "difficulty": "beginner"|"intermediate"|"advanced" if inferable (null otherwise)\n'
    "Only include fields you are confident about. Respond with JSON only."
)


async def _parse_target_description(client: Any, description: str) -> dict[str, Any]:
    """Use Haiku to extract BPM/difficulty from free-text target descriptions."""
    from engine.orchestration.quick_llm import quick_llm_json
    return await quick_llm_json(
        client,
        f"Extract structured fields from this guitar practice target:\n\n{description}",
        system=_TARGET_PARSE_SYSTEM,
    )


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
    collector = get_collector()

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
    await collector.record("session.start", session_id, {"timestamp": time.time()})

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
                model=settings.claude_model,
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

                # Inject session context into audio_analysis args
                if tool_name == "audio_analysis":
                    # Inject pending audio from server-side storage
                    if sess.pending_audio_b64 and "audio_b64" not in args:
                        args["audio_b64"] = sess.pending_audio_b64
                        sess.pending_audio_b64 = None  # consumed
                    if sess.target.target_bpm and "target_bpm" not in args:
                        args["target_bpm"] = sess.target.target_bpm
                    if sess.target.target_notes and "target_notes" not in args:
                        args["target_notes"] = sess.target.target_notes
                    prev_state = sess.state
                    mode = args.get("mode", "quick")
                    target = (
                        SessionState.PROCESSING_DEEP if mode == "deep"
                        else SessionState.PROCESSING_QUICK
                    )
                    if sess.transition(target):
                        await emit_state(prev_state)
                    else:
                        logger.warning(
                            "Invalid state transition %s → %s, forcing",
                            prev_state.value, target.value,
                        )
                        sess.force_state(target)
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

                # Post-process audio_analysis: confidence gate + mastery gate
                if tool_name == "audio_analysis" and "performance_scores" in result:
                    # Track first feedback time
                    if sess.first_feedback_at is None:
                        sess.first_feedback_at = time.time()

                    analysis_confidence = float(result.get("analysis_confidence", 0.0))
                    capture_quality = result.get("capture_quality", {})

                    # Telemetry: feedback delivery timing
                    await collector.record("feedback_delivered", session_id, {
                        "time_to_first_feedback_ms": round(
                            (sess.first_feedback_at - sess.created_at) * 1000, 1
                        ) if sess.first_feedback_at else None,
                        "mode": mode,
                    })

                    if analysis_confidence < sess.mastery_gate.confidence_gate:
                        # Confidence too low → CAPTURE_INVALID
                        prev_state = sess.state
                        sess.transition(SessionState.CAPTURE_INVALID)
                        await emit_state(prev_state)
                        await send(CaptureInvalidMessage(
                            analysis_confidence=analysis_confidence,
                            capture_quality=capture_quality.get("overall", "unknown") if isinstance(capture_quality, dict) else "unknown",
                            reasons=result.get("warnings", []),
                        ))
                        await collector.record("capture_failure", session_id, {
                            "analysis_confidence": analysis_confidence,
                            "capture_quality": capture_quality.get("overall", "unknown") if isinstance(capture_quality, dict) else "unknown",
                            "reasons": result.get("warnings", []),
                        })
                    else:
                        mastery_check = sess.record_attempt(result)
                        result["_mastery"] = mastery_check.to_dict()
                        scores = result.get("performance_scores", {})

                        await collector.record("attempt", session_id, {
                            "attempt_number": mastery_check.attempt.attempt_number,
                            "timing_score": scores.get("timing", 0),
                            "notes_score": scores.get("notes", 0),
                            "overall_score": scores.get("overall", 0),
                            "analysis_confidence": analysis_confidence,
                            "passed": mastery_check.passed_this_attempt,
                            "mode": mode,
                        })

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
                            await collector.record("mastery", session_id, {
                                "total_attempts": len(sess.mastery_gate.attempts),
                                "time_to_mastery_s": round(time.time() - sess.created_at, 1),
                                "passage_description": sess.target.description or "",
                            })
                        else:
                            prev_state = sess.state
                            sess.transition(
                                SessionState.FEEDBACK_DEEP if mode == "deep"
                                else SessionState.FEEDBACK_QUICK
                            )
                            await emit_state(prev_state)

                # coaching_response with a drill → transition to DRILL_ASSIGNED
                if tool_name == "coaching_response" and result.get("drill"):
                    prev_state = sess.state
                    if sess.transition(SessionState.DRILL_ASSIGNED):
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
                # Resolve preset if provided
                preset_id = msg.get("preset_id")
                description = msg.get("description", "")
                target_bpm = msg.get("target_bpm")
                target_notes = msg.get("target_notes")
                difficulty = msg.get("difficulty", "beginner")

                # Haiku-powered free-text parsing: extract BPM/difficulty
                # hints from natural language when not explicitly provided
                if description and not preset_id and (target_bpm is None or difficulty == "beginner"):
                    try:
                        parsed = await _parse_target_description(client, description)
                        if target_bpm is None and parsed.get("bpm"):
                            target_bpm = parsed["bpm"]
                        if difficulty == "beginner" and parsed.get("difficulty"):
                            difficulty = parsed["difficulty"]
                        # Optionally clean the description
                        if parsed.get("clean_description"):
                            description = parsed["clean_description"]
                    except Exception:
                        logger.debug("Haiku target parsing skipped", exc_info=True)

                if preset_id:
                    from presets import get_preset
                    preset = get_preset(preset_id)
                    if preset:
                        description = description or preset["description"]
                        target_bpm = target_bpm or preset["target_bpm"]
                        target_notes = target_notes or preset["target_notes"]
                        difficulty = difficulty or preset["difficulty"]
                    else:
                        await send(TargetValidationMessage(
                            valid=False,
                            errors=[f"Unknown preset: {preset_id}"],
                        ))
                        continue

                prev = sess.state
                validation = sess.set_target(
                    description=description,
                    target_bpm=target_bpm,
                    target_notes=target_notes,
                    difficulty=difficulty,
                )

                if not validation.valid:
                    await send(TargetValidationMessage(
                        valid=False,
                        errors=validation.errors,
                        warnings=validation.warnings,
                    ))
                    continue

                if validation.warnings:
                    await send(TargetValidationMessage(
                        valid=True,
                        warnings=validation.warnings,
                    ))

                await emit_state(prev)
                await collector.record("target.set", session_id, {
                    "description": description,
                    "bpm": target_bpm,
                    "difficulty": difficulty,
                })
                # Acknowledge to Claude so it can greet the user with the target
                warning_text = (
                    f" (Warnings: {'; '.join(validation.warnings)})"
                    if validation.warnings else ""
                )
                user_content = [{
                    "type": "text",
                    "text": (
                        f"Target passage set: {description}"
                        + (f" at {target_bpm} BPM" if target_bpm else "")
                        + f". Difficulty: {difficulty}."
                        + warning_text
                        + " Acknowledge the target and tell the user to record a take when ready."
                    ),
                }]
                await handle_turn(user_content, _system_with_context())

            elif msg_type == "input.text":
                user_content = [{"type": "text", "text": msg["text"]}]
                await handle_turn(user_content, _system_with_context())

            elif msg_type == "input.audio_recording":
                # Full WAV buffer from the recording button — trigger audio analysis.
                # Audio is stored server-side on the session to avoid inflating
                # Claude's conversation history with a ~1 MB base64 blob.
                audio_b64: str = msg["audio_b64"]
                duration_s: float | None = msg.get("duration_s")
                sess.pending_audio_b64 = audio_b64
                prev = sess.state
                sess.transition(SessionState.RECORDING)
                await emit_state(prev)
                user_content = [{
                    "type": "text",
                    "text": (
                        f"The user just recorded a guitar take"
                        + (f" ({duration_s:.1f}s)" if duration_s else "")
                        + ". The audio is held server-side. "
                        "Call audio_analysis with mode='quick' to score the take — "
                        "the audio_b64 will be injected automatically."
                    ),
                }]
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
        await collector.record("session.end", session_id, {
            "duration_s": round(time.time() - sess.created_at, 1),
        })
        drop_session(session_id)
        await send(SessionEndedMessage())
        await send(StatusMessage(state="ended"))
        await send(LogMessage(event="session.ended", timestamp=now()))

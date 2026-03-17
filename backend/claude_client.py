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

    # Conversation history (stateful across turns in this session)
    messages: list[dict[str, Any]] = []

    async def send(msg: Any) -> None:
        payload = msg.model_dump() if hasattr(msg, "model_dump") else msg
        await websocket.send_text(json.dumps(payload))

    def now() -> str:
        return datetime.now(timezone.utc).isoformat()

    # ── Handshake ─────────────────────────────────────────────────────────────
    await send(StatusMessage(state="connecting"))
    await send(SessionStartedMessage(session_id=session_id))
    await send(StatusMessage(state="live"))
    await send(LogMessage(
        event="session.started",
        data={"session_id": session_id},
        timestamp=now(),
    ))

    # ── Per-turn tool-use loop ─────────────────────────────────────────────────

    async def handle_turn(user_content: list[dict[str, Any]]) -> None:
        """
        Append a user turn and run the Claude agentic loop until end_turn.
        Streams text deltas to the client and executes any tool calls.
        """
        messages.append({"role": "user", "content": user_content})

        while True:
            full_text = ""

            # Stream this Claude call
            async with client.messages.stream(
                model="claude-opus-4-6",
                max_tokens=4096,
                system=system_instruction or None,
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

            elif msg_type == "input.text":
                user_content = [{"type": "text", "text": msg["text"]}]
                await handle_turn(user_content)

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
                await handle_turn(user_content)

            elif msg_type == "input.interrupt":
                # Claude Messages API is turn-based; we can only acknowledge.
                await send(LogMessage(event="input.interrupt", timestamp=now()))

    except Exception as exc:
        logger.exception("Claude session error")
        try:
            await send(ErrorMessage(message=str(exc), code="CLAUDE_ERROR"))
            await send(StatusMessage(state="error"))
        except Exception:
            pass
    finally:
        await send(SessionEndedMessage())
        await send(StatusMessage(state="ended"))
        await send(LogMessage(event="session.ended", timestamp=now()))

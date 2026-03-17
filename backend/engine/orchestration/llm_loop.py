"""
Generic agentic tool-use loop for Anthropic Messages API.

Extracted from claude_client.py. The loop structure is domain-agnostic:
stream response → collect tool_use blocks → execute tools → feed results back.

Domain-specific behavior is injected via callbacks.
"""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable, Optional


async def run_agentic_loop(
    client: Any,  # AsyncAnthropic
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    system: str | None,
    *,
    model: str = "claude-opus-4-6",
    max_tokens: int = 4096,
    on_text_delta: Callable[[str], Awaitable[None]],
    on_text_done: Callable[[str], Awaitable[None]],
    on_tool_call: Callable[[str, str, dict], Awaitable[None]],
    on_tool_result: Callable[[str, str, dict, Any], Awaitable[None]],
    tool_executor: Callable[[str, dict], Any],
    pre_tool_hook: Optional[Callable[[str, dict], Awaitable[dict]]] = None,
    post_tool_hook: Optional[Callable[[str, dict, Any], Awaitable[Any]]] = None,
) -> None:
    """
    Run the agentic loop until Claude's stop_reason is end_turn.

    Callbacks:
        on_text_delta: called for each text chunk
        on_text_done: called when a text turn completes
        on_tool_call: called before tool execution (for logging/state updates)
        on_tool_result: called after tool execution (for logging/state updates)
        tool_executor: executes a tool call and returns the result
        pre_tool_hook: optional, transforms args before execution
        post_tool_hook: optional, transforms result after execution
    """
    while True:
        full_text = ""

        async with client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            tools=tools,
            thinking={"type": "adaptive"},
        ) as stream:
            async for text in stream.text_stream:
                full_text += text
                await on_text_delta(text)

            final = await stream.get_final_message()

        if full_text:
            await on_text_done(full_text)

        # Build assistant content and collect tool_use blocks
        assistant_content: list[dict[str, Any]] = []
        tool_uses: list[dict[str, Any]] = []

        for block in final.content:
            if block.type == "thinking":
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

        # No tools → done with this turn
        if not tool_uses:
            break

        # Execute tools and gather results
        tool_results: list[dict[str, Any]] = []
        for tu in tool_uses:
            call_id: str = tu["id"]
            tool_name: str = tu["name"]
            args: dict[str, Any] = tu["input"]

            # Pre-tool hook (e.g. inject session context)
            if pre_tool_hook:
                args = await pre_tool_hook(tool_name, args)

            await on_tool_call(call_id, tool_name, args)

            result = tool_executor(tool_name, args)

            # Post-tool hook (e.g. mastery gate, telemetry)
            if post_tool_hook:
                result = await post_tool_hook(tool_name, args, result)

            await on_tool_result(call_id, tool_name, args, result)

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": call_id,
                "content": json.dumps(result),
            })

        messages.append({"role": "user", "content": tool_results})

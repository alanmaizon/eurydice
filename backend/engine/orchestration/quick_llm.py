"""
Lightweight single-shot LLM utility for cheap, fast tasks.

Uses Haiku by default for per-request work like:
- parsing free-text into structured fields
- classification (technique vs rhythm question)
- simple rubric evaluation

Returns parsed JSON or raw text. No tool use, no streaming, no agentic loop.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def quick_llm_json(
    client: Any,  # AsyncAnthropic
    prompt: str,
    *,
    model: str | None = None,
    system: str | None = None,
    max_tokens: int = 1024,
) -> dict[str, Any]:
    """
    Send a single prompt, expect a JSON object back.

    Falls back to the configured Haiku model if no model is specified.
    Raises ValueError if the response isn't valid JSON.
    """
    if model is None:
        from config import settings
        model = settings.claude_haiku_model

    messages = [{"role": "user", "content": prompt}]

    response = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system or "Respond with valid JSON only. No markdown, no explanation.",
        messages=messages,
    )

    text = response.content[0].text.strip()

    # Strip markdown fences if the model wraps output
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json) and last line (```)
        lines = [l for l in lines[1:] if l.strip() != "```"]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("quick_llm_json: invalid JSON from %s: %s", model, text[:200])
        raise ValueError(f"LLM returned invalid JSON: {e}") from e


async def quick_llm_text(
    client: Any,  # AsyncAnthropic
    prompt: str,
    *,
    model: str | None = None,
    system: str | None = None,
    max_tokens: int = 1024,
) -> str:
    """
    Send a single prompt, return raw text response.
    """
    if model is None:
        from config import settings
        model = settings.claude_haiku_model

    messages = [{"role": "user", "content": prompt}]

    response = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )

    return response.content[0].text.strip()

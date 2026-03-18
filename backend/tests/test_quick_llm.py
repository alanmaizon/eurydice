"""Tests for engine.orchestration.quick_llm — single-shot Haiku utility."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock


def _make_mock_client(response_text: str) -> MagicMock:
    """Create a mock AsyncAnthropic that returns the given text."""
    client = MagicMock()
    content_block = MagicMock()
    content_block.text = response_text
    response = MagicMock()
    response.content = [content_block]
    client.messages.create = AsyncMock(return_value=response)
    return client


@pytest.mark.asyncio
async def test_quick_llm_json_parses_valid_json():
    from engine.orchestration.quick_llm import quick_llm_json

    payload = {"bpm": 120, "difficulty": "intermediate"}
    client = _make_mock_client(json.dumps(payload))

    result = await quick_llm_json(client, "test prompt", model="test-model")

    assert result == payload
    client.messages.create.assert_awaited_once()
    call_kwargs = client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "test-model"


@pytest.mark.asyncio
async def test_quick_llm_json_strips_markdown_fences():
    from engine.orchestration.quick_llm import quick_llm_json

    raw = '```json\n{"bpm": 90}\n```'
    client = _make_mock_client(raw)

    result = await quick_llm_json(client, "test", model="test-model")
    assert result == {"bpm": 90}


@pytest.mark.asyncio
async def test_quick_llm_json_raises_on_invalid_json():
    from engine.orchestration.quick_llm import quick_llm_json

    client = _make_mock_client("not json at all")

    with pytest.raises(ValueError, match="invalid JSON"):
        await quick_llm_json(client, "test", model="test-model")


@pytest.mark.asyncio
async def test_quick_llm_text_returns_raw():
    from engine.orchestration.quick_llm import quick_llm_text

    client = _make_mock_client("  hello world  ")

    result = await quick_llm_text(client, "test", model="test-model")
    assert result == "hello world"


@pytest.mark.asyncio
async def test_parse_target_description():
    """Integration test for _parse_target_description using mocked Haiku."""
    from claude_client import _parse_target_description

    payload = {
        "clean_description": "Comfortably Numb intro solo",
        "bpm": 126,
        "difficulty": "intermediate",
    }
    client = _make_mock_client(json.dumps(payload))

    result = await _parse_target_description(
        client, "Comfortably Numb intro solo at 126 BPM, intermediate level"
    )

    assert result["bpm"] == 126
    assert result["difficulty"] == "intermediate"
    assert "126" not in result["clean_description"]

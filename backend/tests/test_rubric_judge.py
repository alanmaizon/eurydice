"""Tests for engine.evaluation.rubric_judge — Haiku-powered coaching evaluator."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from engine.evaluation.rubric_judge import (
    RubricItem,
    EvalResult,
    JudgmentResult,
    judge_coaching,
    EURYDICE_COACHING_RUBRICS,
)


def _make_mock_client(responses: list[str]) -> MagicMock:
    """Mock client that returns different responses for sequential calls."""
    client = MagicMock()
    side_effects = []
    for text in responses:
        content_block = MagicMock()
        content_block.text = text
        response = MagicMock()
        response.content = [content_block]
        side_effects.append(response)
    client.messages.create = AsyncMock(side_effect=side_effects)
    return client


class TestEvalResult:
    def test_score_empty(self):
        r = EvalResult()
        assert r.score == 0.0
        assert not r.passed_all

    def test_score_all_pass(self):
        r = EvalResult(judgments=[
            JudgmentResult(rubric="a", passed=True, reason="ok"),
            JudgmentResult(rubric="b", passed=True, reason="ok"),
        ])
        assert r.score == 1.0
        assert r.passed_all

    def test_score_partial(self):
        r = EvalResult(judgments=[
            JudgmentResult(rubric="a", passed=True, reason="ok"),
            JudgmentResult(rubric="b", passed=False, reason="nope"),
        ])
        assert r.score == 0.5
        assert not r.passed_all

    def test_to_dict(self):
        r = EvalResult(judgments=[
            JudgmentResult(rubric="a", passed=True, reason="good"),
        ])
        d = r.to_dict()
        assert d["score"] == 1.0
        assert d["passed_all"] is True
        assert d["total"] == 1
        assert d["passed"] == 1


class TestDefaultRubrics:
    def test_has_expected_rubrics(self):
        names = {r.name for r in EURYDICE_COACHING_RUBRICS}
        assert "single_correction" in names
        assert "evidence_based" in names
        assert "drill_prescribed" in names
        assert "success_criterion" in names
        assert "no_bluffing" in names


@pytest.mark.asyncio
async def test_judge_coaching_all_pass():
    rubrics = [
        RubricItem(name="test_a", question="Is this good?"),
        RubricItem(name="test_b", question="Is this focused?"),
    ]
    responses = [
        json.dumps({"passed": True, "reason": "Yes, it's good"}),
        json.dumps({"passed": True, "reason": "Yes, focused"}),
    ]
    client = _make_mock_client(responses)

    result = await judge_coaching(
        client, "Great coaching text", rubrics=rubrics, model="test-model"
    )

    assert result.passed_all
    assert result.score == 1.0
    assert len(result.judgments) == 2


@pytest.mark.asyncio
async def test_judge_coaching_partial_fail():
    rubrics = [
        RubricItem(name="test_a", question="Q1"),
        RubricItem(name="test_b", question="Q2"),
    ]
    responses = [
        json.dumps({"passed": True, "reason": "ok"}),
        json.dumps({"passed": False, "reason": "missing drill"}),
    ]
    client = _make_mock_client(responses)

    result = await judge_coaching(
        client, "Some coaching", rubrics=rubrics, model="test-model"
    )

    assert not result.passed_all
    assert result.score == 0.5
    assert result.judgments[1].reason == "missing drill"


@pytest.mark.asyncio
async def test_judge_coaching_handles_llm_error():
    rubrics = [RubricItem(name="test_a", question="Q1")]
    client = MagicMock()
    client.messages.create = AsyncMock(side_effect=RuntimeError("API down"))

    result = await judge_coaching(
        client, "coaching", rubrics=rubrics, model="test-model"
    )

    assert not result.passed_all
    assert "Judge error" in result.judgments[0].reason


@pytest.mark.asyncio
async def test_judge_coaching_with_tool_results():
    rubrics = [RubricItem(name="evidence", question="Does it reference scores?")]
    responses = [json.dumps({"passed": True, "reason": "References timing score"})]
    client = _make_mock_client(responses)

    tool_results = {"performance_scores": {"timing": 0.82, "notes": 0.75}}

    result = await judge_coaching(
        client,
        "Your timing score was 0.82. Focus on the downbeat.",
        tool_results=tool_results,
        rubrics=rubrics,
        model="test-model",
    )

    assert result.passed_all
    # Verify tool results were included in the prompt
    call_kwargs = client.messages.create.call_args.kwargs
    assert "performance_scores" in call_kwargs["messages"][0]["content"]

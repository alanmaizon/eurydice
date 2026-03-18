"""
Haiku-powered rubric judge for evaluating coaching quality.

Used in eval pipelines to check whether coaching responses meet
quality criteria without expensive Sonnet/Opus calls. Each rubric
is a simple yes/no question that Haiku can answer cheaply.

Example rubrics:
- "Does the response contain exactly one primary correction?"
- "Does the response reference specific tool evidence (scores, timestamps)?"
- "Is a drill prescribed with a clear success criterion?"
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RubricItem:
    """A single yes/no evaluation criterion."""
    name: str
    question: str
    weight: float = 1.0


@dataclass
class JudgmentResult:
    """Result of judging a single rubric item."""
    rubric: str
    passed: bool
    reason: str


@dataclass
class EvalResult:
    """Aggregate result of judging a coaching response against all rubrics."""
    judgments: list[JudgmentResult] = field(default_factory=list)

    @property
    def score(self) -> float:
        if not self.judgments:
            return 0.0
        passed = sum(1 for j in self.judgments if j.passed)
        return passed / len(self.judgments)

    @property
    def passed_all(self) -> bool:
        return bool(self.judgments) and all(j.passed for j in self.judgments)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 3),
            "passed_all": self.passed_all,
            "total": len(self.judgments),
            "passed": sum(1 for j in self.judgments if j.passed),
            "judgments": [
                {"rubric": j.rubric, "passed": j.passed, "reason": j.reason}
                for j in self.judgments
            ],
        }


# ── Default Eurydice coaching rubrics ─────────────────────────────────────────

EURYDICE_COACHING_RUBRICS: list[RubricItem] = [
    RubricItem(
        name="single_correction",
        question="Does the coaching response focus on exactly ONE primary correction or issue? (Not zero, not multiple competing corrections)",
    ),
    RubricItem(
        name="evidence_based",
        question="Does the coaching response reference specific evidence from tool results (scores, timestamps, note names, confidence values)?",
    ),
    RubricItem(
        name="drill_prescribed",
        question="Does the coaching response include a specific practice drill or exercise?",
    ),
    RubricItem(
        name="success_criterion",
        question="Does the coaching response include a clear, measurable success criterion for the next attempt?",
    ),
    RubricItem(
        name="no_bluffing",
        question="Does the coaching response avoid claiming to have directly listened to audio or making assertions not backed by tool outputs?",
    ),
]


_JUDGE_SYSTEM = (
    "You are a strict quality judge for AI music coaching responses. "
    "Answer the question about the coaching response with a JSON object: "
    '{"passed": true/false, "reason": "one sentence explanation"}. '
    "Be strict. Respond with JSON only."
)


async def judge_coaching(
    client: Any,  # AsyncAnthropic
    coaching_text: str,
    tool_results: dict[str, Any] | None = None,
    rubrics: list[RubricItem] | None = None,
    model: str | None = None,
) -> EvalResult:
    """
    Judge a coaching response against rubrics using Haiku.

    Args:
        client: AsyncAnthropic client
        coaching_text: The coaching response to evaluate
        tool_results: Optional tool results that the coaching was based on
        rubrics: Custom rubrics (defaults to EURYDICE_COACHING_RUBRICS)
        model: Override model (defaults to configured Haiku)
    """
    from engine.orchestration.quick_llm import quick_llm_json

    if rubrics is None:
        rubrics = EURYDICE_COACHING_RUBRICS

    context = f"COACHING RESPONSE:\n{coaching_text}"
    if tool_results:
        import json
        context += f"\n\nTOOL RESULTS THE COACHING WAS BASED ON:\n{json.dumps(tool_results, indent=2)}"

    result = EvalResult()

    for rubric in rubrics:
        prompt = f"{context}\n\nQUESTION: {rubric.question}"
        try:
            judgment = await quick_llm_json(
                client, prompt, system=_JUDGE_SYSTEM, model=model,
            )
            result.judgments.append(JudgmentResult(
                rubric=rubric.name,
                passed=bool(judgment.get("passed", False)),
                reason=judgment.get("reason", ""),
            ))
        except (ValueError, Exception) as e:
            logger.warning("Rubric judge failed for %s: %s", rubric.name, e)
            result.judgments.append(JudgmentResult(
                rubric=rubric.name,
                passed=False,
                reason=f"Judge error: {e}",
            ))

    return result

"""Deterministic policy engine for tutoring-turn orchestration."""

from __future__ import annotations

from ..tools.reference import looks_like_reference_request
from .contracts import TurnPlan, TurnPolicyContext
from ...schemas import TutorMode


class TurnPolicyEngine:
    """Resolves turn policy when ADK is unavailable or a call fails."""

    def choose(self, context: TurnPolicyContext) -> TurnPlan:
        learner_text = context.turn_input.learner_text.strip()
        lower_text = learner_text.lower()

        if learner_text and looks_like_reference_request(learner_text) and not context.target_text:
            return TurnPlan(
                engine="heuristic-fallback",
                stage="tool_preflight",
                rationale=(
                    "Resolve the cited passage first so the tutor can read and ground follow-up help in actual text."
                ),
                preflight_tool_name="resolve_reference",
                preflight_tool_arguments={
                    "reference": learner_text,
                    "preferred_translation_language": context.preferred_response_language,
                },
            )

        if context.mode == TutorMode.morphology_coach or any(
            marker in lower_text
            for marker in ("analysis", "analy", "parse", "morph", "ending", "case", "declension")
        ):
            return TurnPlan(
                engine="heuristic-fallback",
                stage="tool_preflight",
                rationale=(
                    "Run parse_passage first to ground the response in morphology before free-form generation."
                ),
                preflight_tool_name="parse_passage",
                preflight_tool_arguments={
                    "text": context.target_text or learner_text or "No target text provided.",
                    "focus_word": learner_text.split()[-1] if learner_text else None,
                },
            )

        if context.mode == TutorMode.translation_support and learner_text and context.target_text:
            return TurnPlan(
                engine="heuristic-fallback",
                stage="tool_preflight",
                rationale="Run grade_attempt first so translation guidance is anchored to concrete deltas.",
                preflight_tool_name="grade_attempt",
                preflight_tool_arguments={
                    "learner_answer": learner_text,
                    "reference_answer": context.target_text,
                },
            )

        if any(marker in lower_text for marker in ("drill", "practice", "again", "quiz")):
            return TurnPlan(
                engine="heuristic-fallback",
                stage="tool_preflight",
                rationale="Generate a targeted drill before model generation.",
                preflight_tool_name="generate_drill",
                preflight_tool_arguments={
                    "mistake_summary": learner_text or "Learner requested more practice.",
                    "mode": context.mode.value,
                },
            )

        reason_bits = []
        if context.turn_input.audio_chunk_count:
            reason_bits.append(f"{context.turn_input.audio_chunk_count} audio chunk(s)")
        if context.turn_input.image_frame_count:
            reason_bits.append(f"{context.turn_input.image_frame_count} image frame(s)")
        medium = ", ".join(reason_bits) or "text-only input"

        return TurnPlan(
            engine="heuristic-fallback",
            stage="direct_generation",
            rationale=(
                "No preflight tool selected; continue with direct generation. "
                f"Observed turn medium: {medium}. "
                f"Preferred response language: {context.preferred_response_language}."
            ),
        )

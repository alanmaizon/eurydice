import asyncio

from backend.app.agents.orchestration.live_turns import LiveTurnInput, LiveTurnOrchestrator
from backend.app.schemas import TutorMode
from backend.app.settings import Settings


def test_plan_turn_selects_parse_for_morphology_mode() -> None:
    orchestrator = LiveTurnOrchestrator(Settings())
    plan = asyncio.run(
        orchestrator.plan_turn(
            mode=TutorMode.morphology_coach,
            target_text="logos gar didaskalos",
            preferred_response_language="English",
            turn_input=LiveTurnInput(
                turn_id="turn-1",
                reason="done",
                learner_text="please parse logos",
                audio_chunk_count=2,
                image_frame_count=0,
            ),
        )
    )
    assert plan.stage == "tool_preflight"
    assert plan.preflight_tool_name == "parse_passage"


def test_plan_turn_selects_reference_resolution_for_reference_input() -> None:
    orchestrator = LiveTurnOrchestrator(Settings())
    plan = asyncio.run(
        orchestrator.plan_turn(
            mode=TutorMode.guided_reading,
            target_text=None,
            preferred_response_language="English",
            turn_input=LiveTurnInput(
                turn_id="turn-reference",
                reason="done",
                learner_text="Mark 1:1",
                audio_chunk_count=0,
                image_frame_count=0,
            ),
        )
    )
    assert plan.stage == "tool_preflight"
    assert plan.preflight_tool_name == "resolve_reference"


def test_plan_turn_selects_grade_for_translation_mode() -> None:
    orchestrator = LiveTurnOrchestrator(Settings())
    plan = asyncio.run(
        orchestrator.plan_turn(
            mode=TutorMode.translation_support,
            target_text="the word became flesh",
            preferred_response_language="English",
            turn_input=LiveTurnInput(
                turn_id="turn-2",
                reason="done",
                learner_text="the word was flesh",
                audio_chunk_count=0,
                image_frame_count=0,
            ),
        )
    )
    assert plan.stage == "tool_preflight"
    assert plan.preflight_tool_name == "grade_attempt"


def test_plan_turn_can_choose_direct_generation() -> None:
    orchestrator = LiveTurnOrchestrator(Settings())
    plan = asyncio.run(
        orchestrator.plan_turn(
            mode=TutorMode.guided_reading,
            target_text=None,
            preferred_response_language="English",
            turn_input=LiveTurnInput(
                turn_id="turn-3",
                reason="done",
                learner_text="",
                audio_chunk_count=1,
                image_frame_count=1,
            ),
        )
    )
    assert plan.stage == "direct_generation"
    assert plan.preflight_tool_name is None


def test_plan_turn_selects_parse_for_analysis_request() -> None:
    orchestrator = LiveTurnOrchestrator(Settings(use_google_adk=False))
    plan = asyncio.run(
        orchestrator.plan_turn(
            mode=TutorMode.guided_reading,
            target_text="εἰς τὴν ἔρημον",
            preferred_response_language="English",
            turn_input=LiveTurnInput(
                turn_id="turn-analysis",
                reason="done",
                learner_text="analysis",
                audio_chunk_count=0,
                image_frame_count=0,
            ),
        )
    )
    assert plan.stage == "tool_preflight"
    assert plan.preflight_tool_name == "parse_passage"

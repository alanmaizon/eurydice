from backend.app.agents.tools.runtime import ToolExecutionError, execute_tool_call


def test_parse_tool_returns_analysis() -> None:
    result = execute_tool_call(
        "parse_passage",
        {
            "text": "logos gar didaskalos",
            "focus_word": "logos",
        },
    )
    assert result["tool"] == "parse_passage"
    assert result["status"] == "ok"
    assert result["analysis"]["part_of_speech"] in {"noun_or_adjective", "verb", "unknown"}


def test_resolve_reference_tool_returns_passage_text() -> None:
    result = execute_tool_call(
        "resolve_reference",
        {
            "reference": "Mark 1:1",
            "preferred_translation_language": "English",
        },
    )
    assert result["tool"] == "resolve_reference"
    assert result["status"] == "ok"
    assert result["normalized_reference"] == "mark 1:1"
    assert result["source"] != "starter_corpus"
    assert result["cts_urn"].endswith(":1.1")
    assert "εὐαγγελίου" in result["resolved_text"]


def test_resolve_reference_tool_returns_not_found_for_unknown_reference() -> None:
    result = execute_tool_call(
        "resolve_reference",
        {
            "reference": "Mark 99:99",
        },
    )
    assert result["tool"] == "resolve_reference"
    assert result["status"] == "not_found"
    assert result["work"] == "Mark"


def test_grade_tool_scores_against_reference() -> None:
    result = execute_tool_call(
        "grade_attempt",
        {
            "learner_answer": "the word became flesh",
            "reference_answer": "the word became flesh",
        },
    )
    assert result["tool"] == "grade_attempt"
    assert result["status"] == "ok"
    assert result["score"] >= 90
    assert result["band"] in {"excellent", "good"}


def test_drill_tool_generates_drill() -> None:
    result = execute_tool_call(
        "generate_drill",
        {
            "mistake_summary": "Learner confused the case ending on the subject noun.",
            "mode": "morphology_coach",
            "focus_word": "logos",
        },
    )
    assert result["tool"] == "generate_drill"
    assert result["status"] == "ok"
    assert result["drill_type"] == "morphology_repair"
    assert len(result["drill"]["steps"]) == 3


def test_unknown_tool_raises_execution_error() -> None:
    try:
        execute_tool_call("unknown_tool", {})
    except ToolExecutionError:
        return
    raise AssertionError("Expected ToolExecutionError for unknown tool")

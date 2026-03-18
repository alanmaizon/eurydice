"""
Regression tests for _make_spoken_safe().

Verifies that:
- visual-only fields are stripped from the model-facing tool response
- the frontend-facing full result is not mutated
- non-dict results pass through unchanged
- unknown tool names pass through unchanged

Run:
    cd backend && python -m pytest tests/test_spoken_safe.py -v
"""

# Import the real production functions — tests verify actual behavior, not local copies.
from gemini_client import _make_spoken_safe


# ── parse_greek ───────────────────────────────────────────────────────────────

FULL_PARSE = {
    "word": "εἰμί",
    "lemma": "εἰμί",
    "transliteration": "eimí",
    "part_of_speech": "Verb",
    "tense": "Present",
    "voice": "Active",
    "mood": "Indicative",
    "person": "1st",
    "number": "Singular",
    "definition": "to be, exist",
    "principal_parts": "εἰμί, ἔσομαι, ἦν",
    "ipa": "/eː.mí/",
    "notes": "Most common Greek verb.",
}


class TestParseGreekSpokenSafe:
    def test_strips_transliteration(self):
        safe = _make_spoken_safe("parse_greek", FULL_PARSE)
        assert "transliteration" not in safe

    def test_strips_ipa(self):
        safe = _make_spoken_safe("parse_greek", FULL_PARSE)
        assert "ipa" not in safe

    def test_strips_principal_parts(self):
        safe = _make_spoken_safe("parse_greek", FULL_PARSE)
        assert "principal_parts" not in safe

    def test_keeps_grammatical_fields(self):
        safe = _make_spoken_safe("parse_greek", FULL_PARSE)
        for field in ("word", "lemma", "part_of_speech", "tense", "voice",
                      "mood", "person", "number", "definition"):
            assert field in safe, f"expected {field!r} to be kept"

    def test_keeps_notes(self):
        safe = _make_spoken_safe("parse_greek", FULL_PARSE)
        assert "notes" in safe

    def test_does_not_mutate_original(self):
        import copy
        original = copy.deepcopy(FULL_PARSE)
        _make_spoken_safe("parse_greek", FULL_PARSE)
        assert FULL_PARSE == original


# ── lookup_lexicon ────────────────────────────────────────────────────────────

FULL_LEXICON = {
    "lemma": "μῆνις",
    "transliteration": "mēnis",
    "part_of_speech": "Noun, Feminine, 3rd declension",
    "definitions": ["wrath, rage (esp. of the gods)", "lasting anger"],
    "usage": "Rare outside epic.",
    "key_refs": ["Il. 1.1", "Il. 1.75"],
    "principal_parts": None,
}


class TestLookupLexiconSpokenSafe:
    def test_strips_transliteration(self):
        safe = _make_spoken_safe("lookup_lexicon", FULL_LEXICON)
        assert "transliteration" not in safe

    def test_strips_key_refs(self):
        safe = _make_spoken_safe("lookup_lexicon", FULL_LEXICON)
        assert "key_refs" not in safe

    def test_strips_principal_parts(self):
        safe = _make_spoken_safe("lookup_lexicon", FULL_LEXICON)
        assert "principal_parts" not in safe

    def test_keeps_definitions_and_usage(self):
        safe = _make_spoken_safe("lookup_lexicon", FULL_LEXICON)
        assert "definitions" in safe
        assert "usage" in safe
        assert "lemma" in safe
        assert "part_of_speech" in safe


# ── scan_meter ────────────────────────────────────────────────────────────────

FULL_SCANSION = {
    "line": "μῆνιν ἄειδε θεά",
    "meter": "Dactylic Hexameter",
    "pattern": "— ∪∪ | — — | — ∪∪",
    "analysis": "Foot 1: spondee; typical Iliadic opening rhythm.",
}


class TestScanMeterSpokenSafe:
    def test_strips_pattern(self):
        safe = _make_spoken_safe("scan_meter", FULL_SCANSION)
        assert "pattern" not in safe

    def test_strips_analysis(self):
        # analysis can be a complex foot-by-foot array; strip it so the model
        # cannot narrate all six foot breakdowns verbatim
        safe = _make_spoken_safe("scan_meter", FULL_SCANSION)
        assert "analysis" not in safe

    def test_keeps_meter_and_line(self):
        safe = _make_spoken_safe("scan_meter", FULL_SCANSION)
        assert "meter" in safe
        assert "line" in safe


# ── edge cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_non_dict_passes_through(self):
        assert _make_spoken_safe("parse_greek", "raw string") == "raw string"
        assert _make_spoken_safe("parse_greek", 42) == 42
        assert _make_spoken_safe("parse_greek", None) is None

    def test_unknown_tool_passes_through(self):
        payload = {"foo": "bar", "transliteration": "should_stay"}
        safe = _make_spoken_safe("unknown_tool", payload)
        assert safe == payload

    def test_empty_dict_passes_through(self):
        assert _make_spoken_safe("parse_greek", {}) == {}

    def test_result_with_error_field_preserved(self):
        payload = {**FULL_PARSE, "_error": "something went wrong"}
        safe = _make_spoken_safe("parse_greek", payload)
        assert "_error" in safe  # error info should reach the model

    def test_partial_result_missing_visual_fields(self):
        # Should not crash if the visual-only fields aren't present
        minimal = {"word": "ἦν", "lemma": "εἰμί", "definition": "was"}
        safe = _make_spoken_safe("parse_greek", minimal)
        assert safe == minimal

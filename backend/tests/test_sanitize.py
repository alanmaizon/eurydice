"""
Regression tests for transcript sanitization logic.

Imports the real functions from gemini_client.py to test the actual source of truth.

Run from repo root:
    cd backend && pip install pytest && python -m pytest tests/test_sanitize.py -v
"""

from gemini_client import _sanitize_transcript as sanitize, _TRANSLIT_PARENS_RE


def strip(text: str) -> str:
    """Apply only the transliteration stripping regex."""
    return _TRANSLIT_PARENS_RE.sub(r'\1', text)


# ── stripParentheticalTransliterations (via _TRANSLIT_PARENS_RE) ──────────────

class TestStripTransliterationParens:
    def test_strips_lowercase_transliteration(self):
        assert strip("εἰμί (eimi)") == "εἰμί"

    def test_strips_capitalized_transliteration(self):
        assert strip("Πνεῦμα (Pneuma)") == "Πνεῦμα"

    def test_strips_polytonic_greek(self):
        assert strip("λόγος (logos)") == "λόγος"

    def test_strips_mid_sentence(self):
        result = strip("The lemma is εἰμί (eimi), the verb to be.")
        assert result == "The lemma is εἰμί, the verb to be."

    def test_strips_multiple_occurrences(self):
        result = strip("εἰμί (eimi) and λόγος (logos)")
        assert result == "εἰμί and λόγος"

    def test_preserves_prose_parens_no_greek(self):
        assert strip("Peter (not Paul)") == "Peter (not Paul)"

    def test_preserves_multiword_parenthetical_after_greek(self):
        assert strip("εἰμί (to be)") == "εἰμί (to be)"

    def test_preserves_citation_style_parens(self):
        assert strip("see Homer (Il. 1.1)") == "see Homer (Il. 1.1)"

    def test_no_greek_no_change(self):
        plain = "The quick brown fox (jumps) over."
        assert strip(plain) == plain

    def test_empty_string(self):
        assert strip("") == ""


# ── _sanitize_transcript (full pipeline) ─────────────────────────────────────

class TestSanitizeTranscript:
    def test_removes_ctrl46(self):
        assert sanitize("<ctrl46>hello") == "hello"

    def test_removes_arbitrary_ctrl_token(self):
        assert sanitize("foo<ctrl12>bar") == "foobar"

    def test_ctrl_token_case_insensitive(self):
        assert sanitize("<CTRL46>hi") == "hi"

    def test_strips_transliteration_after_ctrl(self):
        assert sanitize("<ctrl46>εἰμί (eimi)") == "εἰμί"

    def test_strips_transliteration_alone(self):
        assert sanitize("εἰμί (eimi)") == "εἰμί"

    def test_preserves_prose_parens(self):
        assert sanitize("Peter (not Paul)") == "Peter (not Paul)"

    def test_preserves_multiword_parens_after_greek(self):
        assert sanitize("εἰμί (to be)") == "εἰμί (to be)"

    def test_empty_string(self):
        assert sanitize("") == ""

    def test_removes_non_printable_chars(self):
        # \x01 is a non-printable character
        assert sanitize("hello\x01world") == "helloworld"

    def test_idempotent_on_clean_string(self):
        clean = "The word εἰμί means 'to be'."
        assert sanitize(clean) == clean

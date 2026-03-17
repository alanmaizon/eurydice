"""
Regression tests for transcript sanitization logic.

Run from repo root:
    cd backend && pip install pytest && python -m pytest tests/test_sanitize.py -v
"""

import re

# ── Replicate the exact regexes from gemini_client.py ────────────────────────
# Keep these in sync with the source of truth in gemini_client.py.

_CTRL_TOKEN_RE = re.compile(r'<ctrl\d+>', re.IGNORECASE)
_CTRL_CHAR_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\ufeff]')
_TRANSLIT_PARENS_RE = re.compile(
    r'([^\s]*[\u0370-\u03ff\u1f00-\u1fff][^\s]*)\s*\([A-Za-z\u00c0-\u024f\'-]{1,30}\)',
)


def sanitize(raw: str) -> str:
    cleaned = _CTRL_TOKEN_RE.sub('', raw)
    cleaned = _CTRL_CHAR_RE.sub('', cleaned)
    cleaned = _TRANSLIT_PARENS_RE.sub(r'\1', cleaned)
    return cleaned


# ── stripParentheticalTransliterations (via _TRANSLIT_PARENS_RE) ──────────────

def strip(text: str) -> str:
    return _TRANSLIT_PARENS_RE.sub(r'\1', text)


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

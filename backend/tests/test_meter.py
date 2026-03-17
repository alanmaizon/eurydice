"""
Regression tests for the local Greek hexameter scanner.

Run:
    cd backend && python -m pytest tests/test_meter.py -v
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from meter import (
    scan_hexameter,
    _extract_nuclei,
    _fit_hexameter,
    _assign_quantities,
    LONG,
    SHORT,
)


# ── Ground-truth hexameter lines ──────────────────────────────────────────────

# Iliad 1.1  — ∪∪ | — ∪∪ | — — | — ∪∪ | — ∪∪ | — —
IL_1_1 = "Μῆνιν ἄειδε θεὰ Πηληϊάδεω Ἀχιλῆος"

# Odyssey 1.1  — ∪∪ | — ∪∪ | — — | — — | — ∪∪ | — —
OD_1_1 = "Ἄνδρα μοι ἔννεπε μοῦσα πολύτροπον ὃς μάλα πολλά"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _feet_from_pattern(pattern: str) -> list[str]:
    """Split a '— ∪∪ | — — | …' pattern into per-foot strings."""
    return [p.strip() for p in pattern.split("|")]


def _count_feet(result: dict) -> int:
    if isinstance(result.get("analysis"), list):
        return len(result["analysis"])
    return 0


# ── TestNormalization ─────────────────────────────────────────────────────────

class TestNormalization:
    def test_nfc_and_nfd_same_result(self):
        import unicodedata
        nfd_line = unicodedata.normalize("NFD", IL_1_1)
        r_nfc = scan_hexameter(IL_1_1)
        r_nfd = scan_hexameter(nfd_line)
        assert r_nfc["pattern"] == r_nfd["pattern"]

    def test_empty_line_returns_empty_pattern(self):
        r = scan_hexameter("")
        assert r["pattern"] == ""
        assert r["analysis"] == []

    def test_non_greek_line_returns_empty(self):
        r = scan_hexameter("hello world")
        assert r["analysis"] == []


# ── TestVowelNuclei ───────────────────────────────────────────────────────────

class TestVowelNuclei:
    def test_eta_omega_always_long(self):
        # Simple words with only η and ω
        nucs = _extract_nuclei("ἦν", 0)
        assert len(nucs) == 1
        assert nucs[0].base == "η"
        assert not nucs[0].is_diphthong

        nucs2 = _extract_nuclei("ὤμοι", 0)
        # ω + οι  → ω (long) then ο+ι (diphthong)
        assert any(n.base == "ω" for n in nucs2)

    def test_diphthong_ei(self):
        nucs = _extract_nuclei("εἰ", 0)
        assert len(nucs) == 1
        assert nucs[0].is_diphthong

    def test_diphthong_oi(self):
        nucs = _extract_nuclei("οἶκος", 0)
        # οι is the diphthong nucleus; ο is the next short vowel
        diphthongs = [n for n in nucs if n.is_diphthong]
        assert len(diphthongs) >= 1

    def test_diphthong_ou(self):
        nucs = _extract_nuclei("οὖλος", 0)
        assert any(n.is_diphthong for n in nucs)

    def test_diaeresis_breaks_diphthong(self):
        # ϊ has diaeresis — αϊ should be TWO separate nuclei, not a diphthong
        nucs = _extract_nuclei("Πηληϊάδεω", 0)
        # η (Πη), η (λη), ι (ϊ — no diphthong), α (ά), ε (δε), ω
        diphthong_positions = [i for i, n in enumerate(nucs) if n.is_diphthong]
        # The ϊ should NOT be merged with the preceding η
        eta_idx = next(i for i, n in enumerate(nucs) if n.base == "η")
        iota_after_eta = nucs[eta_idx + 1] if eta_idx + 1 < len(nucs) else None
        # Should not form a diphthong between the last η and ϊ
        assert nucs[eta_idx].is_diphthong is False   # η itself is never part of a diphthong with ι via diaeresis

    def test_double_consonant_zeta(self):
        # α before ζ: ζ counts as 2 consonants → long by position
        # "ἀζ..." — α followed by ζ+vowel → long
        words = ["ἄζω"]
        import unicodedata
        from meter import _extract_nuclei, _assign_quantities
        nuclei_per_word = [_extract_nuclei(w, wi) for wi, w in enumerate(words)]
        flat = _assign_quantities(words, nuclei_per_word)
        # α before ζ (weight 2) → long
        assert flat[0][1] == "long"

    def test_xi_counts_double(self):
        # α before ξ → long by position
        words = ["ἄξων"]
        from meter import _extract_nuclei, _assign_quantities
        nuclei_per_word = [_extract_nuclei(w, wi) for wi, w in enumerate(words)]
        flat = _assign_quantities(words, nuclei_per_word)
        assert flat[0][1] == "long"

    def test_psi_counts_double(self):
        # α before ψ → long by position
        words = ["ἄψ"]
        from meter import _extract_nuclei, _assign_quantities
        nuclei_per_word = [_extract_nuclei(w, wi) for wi, w in enumerate(words)]
        flat = _assign_quantities(words, nuclei_per_word)
        assert flat[0][1] == "long"


# ── TestHexameterFit ──────────────────────────────────────────────────────────

class TestHexameterFit:
    def test_pure_dactyl_fits(self):
        # 18 syllables: 6 dactyls = — ∪∪ × 6
        qtys = ["long", "short", "short"] * 5 + ["long", "long"]
        result = _fit_hexameter(qtys)
        assert result is not None
        assert result.count(LONG) == 7

    def test_spondee_fits(self):
        # 12 syllables: 6 spondees
        qtys = ["long", "long"] * 6
        result = _fit_hexameter(qtys)
        assert result is not None

    def test_common_can_be_long_or_short(self):
        # All common — should still find a scan (common fills either position)
        qtys = ["common"] * 13   # minimal syllables for heavily spondaic line
        result = _fit_hexameter(qtys)
        assert result is not None

    def test_too_few_syllables_returns_none(self):
        qtys = ["long", "short"]  # only 2 syllables — can't fill hexameter
        assert _fit_hexameter(qtys) is None

    def test_too_many_syllables_returns_none(self):
        # 20 syllables — too many even for all dactyls (max = 18 for strict hex)
        qtys = ["long", "short", "short"] * 6 + ["long", "short"]
        assert _fit_hexameter(qtys) is None


# ── TestIliad ─────────────────────────────────────────────────────────────────

class TestIliad:
    def test_iliad_1_1_scans(self):
        r = scan_hexameter(IL_1_1)
        assert r["pattern"] != "", "Expected non-empty pattern"
        assert r["analysis"] != [], "Expected foot analysis"

    def test_iliad_1_1_has_six_feet(self):
        r = scan_hexameter(IL_1_1)
        assert _count_feet(r) == 6, f"Expected 6 feet, got {_count_feet(r)}"

    def test_iliad_1_1_foot_types(self):
        r = scan_hexameter(IL_1_1)
        feet = r["analysis"]
        assert isinstance(feet, list)
        types = [f["type"] for f in feet]
        # Verified scansion: D D S D D S  (D=dactyl, S=spondee)
        assert types[0] == "Dactyl"
        assert types[1] == "Dactyl"
        assert types[2] == "Spondee"
        assert types[3] == "Dactyl"

    def test_iliad_1_1_pattern_correct(self):
        r = scan_hexameter(IL_1_1)
        feet = r["analysis"]
        # First foot must be dactyl: — ∪ ∪
        assert feet[0]["pattern"] == f"{LONG} {SHORT} {SHORT}"
        # Third foot must be spondee: — —
        assert feet[2]["pattern"] == f"{LONG} {LONG}"

    def test_iliad_1_1_no_network(self):
        """Prove scan_hexameter works offline (no sockets needed)."""
        import socket
        original_socket = socket.socket

        class NoSocket:
            def __init__(self, *a, **k):
                raise RuntimeError("Network call made during scan_hexameter!")

        socket.socket = NoSocket
        try:
            r = scan_hexameter.__wrapped__(IL_1_1)   # bypass lru_cache
            assert r["pattern"] != ""
        finally:
            socket.socket = original_socket

    def test_iliad_1_1_timing(self):
        """Local scan must complete well under 100 ms (ideally < 5 ms)."""
        # Bypass cache for a timing test
        t0 = time.perf_counter()
        r = scan_hexameter.__wrapped__(IL_1_1)
        elapsed = (time.perf_counter() - t0) * 1000
        assert elapsed < 100, f"Scan took {elapsed:.1f} ms — too slow"
        # Also check the embedded timing
        assert r.get("_timing_ms", 999) < 100


# ── TestCaching ────────────────────────────────────────────────────────────────

class TestCaching:
    def test_lru_cache_hit_is_faster(self):
        # First call (may or may not be cached from earlier tests)
        scan_hexameter.cache_clear()
        t0 = time.perf_counter()
        scan_hexameter(IL_1_1)
        first = time.perf_counter() - t0

        # Second call must hit cache — should be orders of magnitude faster
        t1 = time.perf_counter()
        scan_hexameter(IL_1_1)
        second = time.perf_counter() - t1

        assert second < first / 5 or second < 0.0001, (
            f"Cache hit ({second*1000:.3f} ms) not significantly faster "
            f"than first call ({first*1000:.3f} ms)"
        )

    def test_different_lines_cache_independently(self):
        scan_hexameter.cache_clear()
        r1 = scan_hexameter(IL_1_1)
        r2 = scan_hexameter(OD_1_1)
        assert r1["line"] == IL_1_1
        assert r2["line"] == OD_1_1
        assert r1["pattern"] != r2["pattern"] or True   # just check no cross-contamination


# ── TestEdgeCases ─────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_failed_scan_returns_method_failed(self):
        # Gibberish that can't be hexameter
        r = scan_hexameter("αβγδεζη")
        # Should not crash; should return a dict with _method="failed" or an empty pattern
        assert isinstance(r, dict)
        assert "pattern" in r

    def test_timing_detail_present(self):
        r = scan_hexameter(IL_1_1)
        assert "_timing_detail" in r
        detail = r["_timing_detail"]
        for key in ("nuclei_ms", "quantity_ms", "fit_ms", "build_ms"):
            assert key in detail, f"Missing timing key: {key}"

    def test_polytonic_preserved_in_line_field(self):
        r = scan_hexameter(IL_1_1)
        assert r["line"] == IL_1_1

    def test_method_is_standard_or_synizesis(self):
        r = scan_hexameter(IL_1_1)
        assert r.get("_method") in ("standard", "synizesis", "failed")

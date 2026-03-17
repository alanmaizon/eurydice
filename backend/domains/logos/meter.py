"""
Fast deterministic Ancient Greek dactylic hexameter scanner.

No LLM calls, no network dependencies.
Expected runtime: < 1 ms for a typical Homeric line.

Algorithm
---------
1. Normalize line to NFC; split into Greek word tokens.
2. Extract vowel nuclei (individual vowels or diphthongs) from each word.
3. Assign initial quantity:
     η, ω          → long by nature
     ε, ο          → short by nature
     diphthongs    → long by nature
     α, ι, υ       → "common" (resolved in step 4)
4. Apply long-by-position: a common-quantity vowel followed by ≥ 2 consonant
   weights (ζ ξ ψ count as 2 each) becomes long.  Cross-word consonant
   clusters are counted.
5. Backtrack over the dactylic hexameter schema:
     Feet 1-5: dactyl (— ∪ ∪) or spondee (— —)
     Foot 6:   spondee (— —) or trochee (— ∪); last position is anceps
6. If step 5 fails, attempt synizesis: merge candidate adjacent nuclei pairs
   (εω, αω, εα, εο, οα) one at a time (or in pairs) and retry.
7. Return a ScansionResult-compatible dict.  The lru_cache makes repeated
   identical calls instantaneous.
"""

import re
import time
import unicodedata
from functools import lru_cache
from itertools import combinations
from typing import NamedTuple

# ── Symbols ────────────────────────────────────────────────────────────────────
LONG  = "—"
SHORT = "∪"

# ── Character classification constants ────────────────────────────────────────
_LONG_BASES   = frozenset("ηω")
_SHORT_BASES  = frozenset("εο")
_COMMON_BASES = frozenset("αιυ")       # quantity determined by position
_VOWEL_BASES  = _LONG_BASES | _SHORT_BASES | _COMMON_BASES
_CONS_BASES   = frozenset("βγδζθκλμνξπρσςτφχψ")
_DOUBLE_CONS  = frozenset("ζξψ")       # each counts as 2 for position

# Diphthong pairs (base of first vowel, base of second vowel).
# Diaeresis on the second vowel breaks the pair — checked separately.
_DIPHTHONG_PAIRS = frozenset([
    ("α", "ι"), ("α", "υ"),
    ("ε", "ι"), ("ε", "υ"),
    ("ο", "ι"), ("ο", "υ"),
    ("υ", "ι"),
    ("η", "υ"),
])

# Synizesis candidates: adjacent nucleus bases that can merge into one long.
_SYNIZESIS_PAIRS = frozenset([
    ("ε", "ω"), ("α", "ω"), ("ε", "α"), ("ε", "ο"), ("ο", "α"),
])

_COMB_DIAERESIS = "\u0308"
_GREEK_TOKEN_RE = re.compile(r"[\u0370-\u03FF\u1F00-\u1FFF]+")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _base(ch: str) -> str:
    """Return lowercase base letter (no combining diacritics)."""
    return unicodedata.normalize("NFD", ch)[0].lower()


def _has_diaeresis(ch: str) -> bool:
    return _COMB_DIAERESIS in unicodedata.normalize("NFD", ch)


def _is_vowel(ch: str) -> bool:
    return _base(ch) in _VOWEL_BASES


def _is_cons(ch: str) -> bool:
    return _base(ch) in _CONS_BASES


# ── Nucleus data ───────────────────────────────────────────────────────────────

class Nucleus(NamedTuple):
    text: str          # original Unicode characters contributing to this vowel sound
    base: str          # NFC base character(s) for classification (lowercase, no diacritics)
    is_diphthong: bool
    word_idx: int


def _extract_nuclei(word: str, word_idx: int) -> list[Nucleus]:
    """Return all vowel nuclei (diphthongs treated as one) for a single word."""
    chars = list(unicodedata.normalize("NFC", word))
    n = len(chars)
    nuclei: list[Nucleus] = []
    i = 0
    while i < n:
        ch = chars[i]
        if not _is_vowel(ch):
            i += 1
            continue
        b1 = _base(ch)
        # Try to form a diphthong with the next vowel (no diaeresis on second)
        if i + 1 < n and _is_vowel(chars[i + 1]) and not _has_diaeresis(chars[i + 1]):
            b2 = _base(chars[i + 1])
            if (b1, b2) in _DIPHTHONG_PAIRS:
                nuclei.append(Nucleus(ch + chars[i + 1], b1 + b2, True, word_idx))
                i += 2
                continue
        nuclei.append(Nucleus(ch, b1, False, word_idx))
        i += 1
    return nuclei


# ── Quantity assignment ────────────────────────────────────────────────────────

def _initial_qty(nuc: Nucleus) -> str:
    if nuc.is_diphthong:
        return "long"
    b = nuc.base
    if b in _LONG_BASES:
        return "long"
    if b in _SHORT_BASES:
        return "short"
    return "common"   # α ι υ — resolved by position


def _cons_weight_after(words: list[str], wi: int, char_pos: int) -> int:
    """
    Count consonant weight starting at char_pos in words[wi], continuing
    into words[wi+1] if needed.  Stop at the first vowel encountered.
    ζ/ξ/ψ count as 2; other consonants count as 1.
    """
    weight = 0
    for w_offset in range(2):          # current word, then next word
        w = unicodedata.normalize("NFC", words[wi + w_offset])
        start = char_pos if w_offset == 0 else 0
        for ch in w[start:]:
            b = _base(ch)
            if b in _VOWEL_BASES:
                return weight          # hit a vowel — stop
            if b in _DOUBLE_CONS:
                weight += 2
            elif b in _CONS_BASES:
                weight += 1
        if wi + w_offset + 1 >= len(words):
            break
    return weight


def _assign_quantities(
    words: list[str],
    nuclei_per_word: list[list[Nucleus]],
) -> list[tuple[Nucleus, str]]:
    """Assign final quantities (long/short/common) to every nucleus."""
    # Flatten: (nucleus, initial_qty, word_idx, char_end_pos_in_word)
    flat: list[tuple[Nucleus, str, int, int]] = []
    for wi, word in enumerate(words):
        nfc = unicodedata.normalize("NFC", word)
        pos = 0
        for nuc in nuclei_per_word[wi]:
            idx = nfc.find(nuc.text, pos)
            if idx == -1:
                idx = pos
            end = idx + len(nuc.text)
            flat.append((nuc, _initial_qty(nuc), wi, end))
            pos = end

    result: list[tuple[Nucleus, str]] = []
    for nuc, qty, wi, end in flat:
        if qty != "common":
            result.append((nuc, qty))
            continue
        # Check long-by-position
        if wi + 1 < len(words):
            w = unicodedata.normalize("NFC", words[wi])
            weight = _cons_weight_after(words, wi, end)
        else:
            w = unicodedata.normalize("NFC", words[wi])
            weight = 0
            for ch in w[end:]:
                b = _base(ch)
                if b in _VOWEL_BASES:
                    break
                if b in _DOUBLE_CONS:
                    weight += 2
                elif b in _CONS_BASES:
                    weight += 1
        result.append((nuc, "long" if weight >= 2 else "common"))
    return result


# ── Hexameter backtracking ─────────────────────────────────────────────────────

def _fit_hexameter(qtys: list[str]) -> list[str] | None:
    """
    Backtrack over 6-foot dactylic hexameter schema.

    Each of feet 1-5 is dactyl (— ∪ ∪) or spondee (— —).
    Foot 6 is spondee (— —) or trochee (— ∪); the last syllable is anceps
    (accepts both long and common/short).

    "common" can fill either a long or a short position.
    Returns flat list of LONG/SHORT markers or None if no scan found.
    """
    n = len(qtys)

    def can_long(q: str) -> bool:
        return q in ("long", "common")

    def can_short(q: str) -> bool:
        return q in ("short", "common")

    def bt(pos: int, foot: int, acc: list[str]) -> list[str] | None:
        if foot == 6:
            return acc if pos == n else None
        if pos >= n:
            return None

        if foot < 5:
            # Try dactyl first (more common in Homer)
            if (pos + 2 < n
                    and can_long(qtys[pos])
                    and can_short(qtys[pos + 1])
                    and can_short(qtys[pos + 2])):
                r = bt(pos + 3, foot + 1, acc + [LONG, SHORT, SHORT])
                if r is not None:
                    return r
            # Try spondee
            if (pos + 1 < n
                    and can_long(qtys[pos])
                    and can_long(qtys[pos + 1])):
                r = bt(pos + 2, foot + 1, acc + [LONG, LONG])
                if r is not None:
                    return r
        else:
            # Foot 6: needs exactly the remaining syllables
            rem = n - pos
            if rem == 2:
                # Spondee (— —) — anceps accepts anything in last position
                if can_long(qtys[pos]):
                    return acc + [LONG, LONG]   # last is anceps, always accept
            elif rem == 1:
                # Monosyllabic last foot (rare but handle gracefully)
                if can_long(qtys[pos]):
                    return acc + [LONG]
        return None

    return bt(0, 0, [])


# ── Synizesis fallback ─────────────────────────────────────────────────────────

def _merge_at(
    nuclei: list[Nucleus],
    qtys: list[str],
    positions: tuple[int, ...],
) -> tuple[list[Nucleus], list[str]]:
    """Merge nuclei at the given (sorted) positions with their successors."""
    mnuc = list(nuclei)
    mqty = list(qtys)
    for offset, pos in enumerate(sorted(positions)):
        idx = pos - offset
        merged = Nucleus(
            mnuc[idx].text + mnuc[idx + 1].text,
            mnuc[idx].base + mnuc[idx + 1].base,
            True,
            mnuc[idx].word_idx,
        )
        mnuc[idx] = merged
        mnuc.pop(idx + 1)
        mqty[idx] = "long"
        mqty.pop(idx + 1)
    return mnuc, mqty


def _try_synizesis(
    nuclei: list[Nucleus],
    qtys: list[str],
) -> tuple[list[Nucleus], list[str]] | None:
    """
    Try merging candidate synizesis pairs until hexameter fits.
    Returns (merged_nuclei, assignment) or None.
    """
    n = len(nuclei)
    candidates = [
        i for i in range(n - 1)
        if (nuclei[i].base[-1], nuclei[i + 1].base[0]) in _SYNIZESIS_PAIRS
    ]
    max_merges = min(len(candidates), 3)
    for r in range(1, max_merges + 1):
        for combo in combinations(candidates, r):
            mn, mq = _merge_at(nuclei, qtys, combo)
            assignment = _fit_hexameter(mq)
            if assignment is not None:
                return mn, assignment
    return None


# ── Foot construction ──────────────────────────────────────────────────────────

def _build_feet(nuclei: list[Nucleus], assignment: list[str]) -> list[dict]:
    """Convert flat nuclei + assignment into structured foot dicts."""
    feet: list[dict] = []
    i = 0
    foot_num = 1
    na = len(assignment)

    while i < na:
        if (i + 2 < na
                and assignment[i] == LONG
                and assignment[i + 1] == SHORT
                and assignment[i + 2] == SHORT):
            feet.append({
                "foot": foot_num,
                "syllables": "·".join(n.text for n in nuclei[i:i + 3]),
                "pattern": f"{LONG} {SHORT} {SHORT}",
                "type": "Dactyl",
                "notes": "",
            })
            i += 3
        elif (i + 1 < na
              and assignment[i] == LONG
              and assignment[i + 1] == LONG):
            feet.append({
                "foot": foot_num,
                "syllables": "·".join(n.text for n in nuclei[i:i + 2]),
                "pattern": f"{LONG} {LONG}",
                "type": "Spondee",
                "notes": "",
            })
            i += 2
        elif (i + 1 < na
              and assignment[i] == LONG
              and assignment[i + 1] == SHORT):
            feet.append({
                "foot": foot_num,
                "syllables": "·".join(n.text for n in nuclei[i:i + 2]),
                "pattern": f"{LONG} {SHORT}",
                "type": "Trochee",
                "notes": "Final anceps",
            })
            i += 2
        else:
            feet.append({
                "foot": foot_num,
                "syllables": nuclei[i].text if i < len(nuclei) else "?",
                "pattern": assignment[i],
                "type": "?",
                "notes": "",
            })
            i += 1
        foot_num += 1

    return feet


# ── Public entry point ─────────────────────────────────────────────────────────

@lru_cache(maxsize=512)
def scan_hexameter(line: str, expected_meter: str = "Dactylic Hexameter") -> dict:
    """
    Scan a line of Ancient Greek dactylic hexameter.

    Cached by (line, expected_meter) — repeated calls for the same line are O(1).
    Returns a ScansionResult-compatible dict.
    """
    t0 = time.perf_counter()

    words = _GREEK_TOKEN_RE.findall(unicodedata.normalize("NFC", line))
    if not words:
        return {
            "line": line, "meter": expected_meter,
            "pattern": "", "analysis": [],
            "_timing_ms": 0.0,
        }

    # 1. Extract nuclei
    nuclei_per_word = [_extract_nuclei(w, wi) for wi, w in enumerate(words)]
    t_nuclei = time.perf_counter()

    # 2. Assign quantities
    flat = _assign_quantities(words, nuclei_per_word)
    flat_nuclei = [n for n, _ in flat]
    flat_qtys   = [q for _, q in flat]
    t_qty = time.perf_counter()

    # 3. Try standard hexameter fit
    method = "standard"
    assignment = _fit_hexameter(flat_qtys)
    use_nuclei = flat_nuclei

    # 4. If failed, try synizesis
    if assignment is None:
        method = "synizesis"
        syn = _try_synizesis(flat_nuclei, flat_qtys)
        if syn is not None:
            use_nuclei, assignment = syn

    t_fit = time.perf_counter()

    # 5. Build output
    if assignment is None:
        # Best-effort: show quantities without foot grouping
        pattern = " ".join(
            LONG if q == "long" else (SHORT if q == "short" else "?")
            for q in flat_qtys
        )
        return {
            "line": line, "meter": expected_meter,
            "pattern": pattern, "analysis": [],
            "_timing_ms": round((t_fit - t0) * 1000, 2),
            "_method": "failed",
            "_note": "Automatic scansion inconclusive",
        }

    feet = _build_feet(use_nuclei, assignment)
    pattern = " | ".join(f["pattern"] for f in feet)

    t_end = time.perf_counter()

    return {
        "line": line,
        "meter": expected_meter,
        "pattern": pattern,
        "analysis": feet,
        "_timing_ms": round((t_end - t0) * 1000, 2),
        "_timing_detail": {
            "nuclei_ms":    round((t_nuclei - t0) * 1000, 3),
            "quantity_ms":  round((t_qty - t_nuclei) * 1000, 3),
            "fit_ms":       round((t_fit - t_qty) * 1000, 3),
            "build_ms":     round((t_end - t_fit) * 1000, 3),
        },
        "_method": method,
    }

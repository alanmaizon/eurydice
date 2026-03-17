"""
Tool definitions and executors for Logos.

In production (non-mock) mode, tool execution uses a separate Gemini call to
generate structured philological data. In mock mode, hardcoded examples are used.
"""

from typing import Any
import asyncio
import json
import time

# ── Tool function declarations (sent to Gemini) ───────────────────────────────

TOOL_DECLARATIONS = [
    {
        "name": "parse_greek",
        "description": (
            "ALWAYS call this function when performing morphological analysis of an Ancient Greek word. "
            "Do NOT write morphology tables or grammatical breakdowns in plain text — invoke this function instead. "
            "Returns part of speech, tense, mood, voice, person, number, gender, case, degree as applicable, "
            "plus lemma, transliteration, definition, and principal parts for verbs."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "word": {
                    "type": "string",
                    "description": "The Greek word to parse, in Unicode Greek",
                },
                "context": {
                    "type": "string",
                    "description": "Optional: the sentence or phrase containing the word",
                },
            },
            "required": ["word"],
        },
    },
    {
        "name": "lookup_lexicon",
        "description": (
            "ALWAYS call this function when providing a lexicon entry or definition for a Greek word. "
            "Do NOT write lexicon entries in plain text — invoke this function instead. "
            "Returns a summary entry with definitions, usage notes, and key references."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "lemma": {
                    "type": "string",
                    "description": "The dictionary form (lemma) of the Greek word",
                }
            },
            "required": ["lemma"],
        },
    },
    {
        "name": "scan_meter",
        "description": (
            "ALWAYS call this function when performing metrical scansion on a line of Greek verse. "
            "Do NOT write scansion patterns in plain text — invoke this function instead. "
            "Returns the scansion pattern, meter type, and any notable features."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "line": {
                    "type": "string",
                    "description": "The line of Greek verse to scan",
                },
                "expected_meter": {
                    "type": "string",
                    "description": "Optional: expected meter type",
                },
            },
            "required": ["line"],
        },
    },
]

# ── Mock results ──────────────────────────────────────────────────────────────

MOCK_PARSES: dict[str, Any] = {
    "μῆνιν": {
        "word": "μῆνιν",
        "lemma": "μῆνις",
        "transliteration": "mēnin",
        "part_of_speech": "Noun",
        "gender": "Feminine",
        "case": "Accusative",
        "number": "Singular",
        "definition": "wrath, rage, anger (of a god or hero)",
        "notes": "Opening word of the Iliad. The accusative singular marks it as the direct object of ἄειδε (sing!).",
    },
    "λύομεν": {
        "word": "λύομεν",
        "lemma": "λύω",
        "transliteration": "lyomen",
        "part_of_speech": "Verb",
        "tense": "Present",
        "voice": "Active",
        "mood": "Indicative",
        "person": "1st",
        "number": "Plural",
        "definition": "we loose / we are loosing",
        "principal_parts": "λύω, λύσω, ἔλυσα, λέλυκα, λέλυμαι, ἐλύθην",
    },
    "ἄνθρωπος": {
        "word": "ἄνθρωπος",
        "lemma": "ἄνθρωπος",
        "transliteration": "anthrōpos",
        "part_of_speech": "Noun",
        "gender": "Masculine",
        "case": "Nominative",
        "number": "Singular",
        "definition": "human being, man (as opposed to gods or animals)",
        "ipa": "/án.tʰrɔː.pos/",
    },
    "ἀλώπηξ": {
        "word": "ἀλώπηξ",
        "lemma": "ἀλώπηξ",
        "transliteration": "alōpēx",
        "part_of_speech": "Noun",
        "gender": "Feminine",
        "case": "Nominative",
        "number": "Singular",
        "definition": "fox (used figuratively of a cunning person)",
        "ipa": "/a.lɔː.pɛːks/",
        "notes": "3rd declension (-πεκ- stem). The fox is the archetypal trickster in Aesop.",
    },
    "κόραξ": {
        "word": "κόραξ",
        "lemma": "κόραξ",
        "transliteration": "korax",
        "part_of_speech": "Noun",
        "gender": "Masculine",
        "case": "Nominative",
        "number": "Singular",
        "definition": "crow, raven",
        "ipa": "/kó.raks/",
        "notes": "3rd declension (-ακ- stem). In Aesop's fable, the crow is duped by the fox's flattery.",
    },
    "default": {
        "word": "—",
        "lemma": "—",
        "transliteration": "—",
        "part_of_speech": "Unknown",
        "definition": "Parse unavailable in mock mode for this word.",
        "notes": "Connect with a live Gemini API key for full morphological analysis.",
    },
}

MOCK_LEXICON: dict[str, Any] = {
    "κόραξ": {
        "lemma": "κόραξ",
        "transliteration": "korax",
        "part_of_speech": "Noun, Masculine, 3rd declension",
        "definitions": [
            "crow, raven",
            "(figuratively) a cunning schemer who is himself easily outwitted",
        ],
        "usage": "Common in Aesop. The crow in Fable 124 holds meat in his beak; the fox flatters him into opening his mouth to 'sing', causing him to drop it.",
        "key_refs": ["Aesop Fab. 124", "Ar. Av. 609"],
    },
    "ἀλώπηξ": {
        "lemma": "ἀλώπηξ",
        "transliteration": "alōpēx",
        "part_of_speech": "Noun, Feminine, 3rd declension",
        "definitions": [
            "fox",
            "(figuratively) a crafty, sly person",
        ],
        "usage": "The archetypal trickster in Greek fable (Aesop) and proverb. Contrast λύκος (wolf, brute force) with ἀλώπηξ (fox, cunning).",
        "key_refs": ["Aesop Fab. 124", "Ar. Eq. 1037", "Pind. P. 2.78"],
    },
    "μῆνις": {
        "lemma": "μῆνις",
        "transliteration": "mēnis",
        "part_of_speech": "Noun, Feminine, 3rd declension",
        "definitions": [
            "wrath, rage (esp. of the gods)",
            "lasting anger, divine displeasure",
        ],
        "usage": "Rare outside epic. Always of superhuman or heroic rage. Contrast θυμός (thumos), the more general word for passion.",
        "key_refs": ["Il. 1.1", "Il. 1.75", "Od. 3.135"],
    },
    "λύω": {
        "lemma": "λύω",
        "transliteration": "lyō",
        "part_of_speech": "Verb",
        "definitions": [
            "to loose, unbind, release",
            "to dissolve, destroy",
            "to ransom",
        ],
        "usage": "Common verb; paradigmatic for learning the -ω conjugation in Attic Greek.",
        "principal_parts": "λύω, λύσω, ἔλυσα, λέλυκα, λέλυμαι, ἐλύθην",
    },
}

MOCK_SCANSION: dict[str, Any] = {
    "μῆνιν ἄειδε θεά Πηληϊάδεω Ἀχιλῆος": {
        "line": "μῆνιν ἄειδε θεά Πηληϊάδεω Ἀχιλῆος",
        "meter": "Dactylic Hexameter",
        "pattern": "— ∪∪ | — — | — ∪∪ | — ∪∪ | — ∪∪ | — —",
        "analysis": "Foot 1: spondee (μῆνιν); Foot 2: spondee; Foot 3: dactyl; typical Iliadic opening rhythm.",
    }
}


# ── Eurydice tool declarations (Anthropic-compatible, used by claude_client.py) ─

EURYDICE_TOOL_DECLARATIONS = [
    {
        "name": "audio_analysis",
        "description": (
            "Analyze a guitar performance recording. "
            "In 'quick' mode returns tempo, onset timing, and pitch scores quickly. "
            "In 'deep' mode additionally runs note transcription (Basic Pitch) and "
            "optional source separation (Demucs). "
            "Always returns confidence values — if confidence is below 0.7 on any key "
            "metric, report it and ask for a cleaner recording rather than guessing. "
            "Call this tool instead of guessing about the user's playing."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["quick", "deep"],
                    "description": "Analysis depth. Use 'quick' first; escalate to 'deep' if needed.",
                },
                "audio_b64": {
                    "type": "string",
                    "description": "Base64-encoded WAV or PCM audio of the guitar performance.",
                },
                "target_bpm": {
                    "type": "number",
                    "description": "Target tempo in BPM for alignment scoring. Optional.",
                },
                "target_notes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "onset_s": {"type": "number"},
                            "midi": {"type": "integer"},
                        },
                        "required": ["onset_s", "midi"],
                    },
                    "description": "Reference note events for note-level scoring. Optional.",
                },
                "has_backing_track": {
                    "type": "boolean",
                    "description": "Set true if the recording contains a backing track; triggers separation in deep mode.",
                },
            },
            "required": ["mode"],
        },
    },
    {
        "name": "vision_analysis",
        "description": (
            "Analyze a photograph or video frame of a guitarist's hands/posture. "
            "Returns detected hand landmarks, handedness, and technique flags such as "
            "collapsed_wrist, excessive_finger_lift, thumb_over_neck, or pick_depth. "
            "Each flag includes severity (low/medium/high) and confidence (0–1). "
            "Only report flags whose confidence >= 0.6. "
            "Call this tool when the user shares a camera image for technique feedback."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "image_b64": {
                    "type": "string",
                    "description": "Base64-encoded JPEG or PNG image of the guitarist.",
                },
                "focus": {
                    "type": "string",
                    "enum": ["fretting_hand", "picking_hand", "both", "posture"],
                    "description": "Which aspect to focus the analysis on.",
                },
            },
            "required": ["image_b64"],
        },
    },
]


# ── Eurydice mock results ──────────────────────────────────────────────────────

MOCK_AUDIO_QUICK: dict[str, Any] = {
    "mode": "quick",
    "tempo_bpm": 92.4,
    "tempo_confidence": 0.87,
    "beat_times_s": [0.0, 0.65, 1.30, 1.95, 2.60],
    "performance_scores": {
        "timing": 0.78,
        "notes": 0.82,
        "overall": 0.80,
    },
    "warnings": [],
    "_note": "Mock result — connect live audio pipeline for real analysis.",
}

MOCK_AUDIO_DEEP: dict[str, Any] = {
    "mode": "deep",
    "tempo_bpm": 92.4,
    "tempo_confidence": 0.87,
    "beat_times_s": [0.0, 0.65, 1.30, 1.95, 2.60],
    "note_events": [
        {"onset_s": 0.02, "offset_s": 0.60, "midi": 52, "confidence": 0.91},
        {"onset_s": 0.68, "offset_s": 1.25, "midi": 54, "confidence": 0.88},
        {"onset_s": 1.33, "offset_s": 1.92, "midi": 55, "confidence": 0.85},
    ],
    "performance_scores": {
        "timing": 0.78,
        "notes": 0.82,
        "overall": 0.80,
    },
    "alignment": {
        "mean_onset_error_ms": 42.0,
        "max_onset_error_ms": 110.0,
        "note_f1": 0.82,
    },
    "warnings": [],
    "_note": "Mock result — connect Basic Pitch + librosa for real transcription.",
}

MOCK_VISION: dict[str, Any] = {
    "hands_detected": 1,
    "handedness": ["left"],
    "technique_flags": [
        {
            "flag": "collapsed_wrist",
            "severity": "medium",
            "confidence": 0.74,
            "description": "Left wrist appears slightly collapsed under the neck. Try arching it outward.",
        }
    ],
    "capture_warnings": [],
    "_note": "Mock result — connect MediaPipe Hands for real landmark detection.",
}


def execute_eurydice_tool_mock(tool_name: str, args: dict[str, Any]) -> Any:
    """Return hardcoded mock results for Eurydice tool calls."""
    if tool_name == "audio_analysis":
        mode = args.get("mode", "quick")
        return MOCK_AUDIO_DEEP if mode == "deep" else MOCK_AUDIO_QUICK
    if tool_name == "vision_analysis":
        return MOCK_VISION
    return {"error": f"Unknown Eurydice tool: {tool_name}"}


# ── Logos mock results (unchanged below) ─────────────────────────────────────

def execute_tool_mock(tool_name: str, args: dict[str, Any]) -> Any:
    """Return hardcoded mock results for tool calls."""
    if tool_name == "parse_greek":
        word = args.get("word", "")
        return MOCK_PARSES.get(word, {**MOCK_PARSES["default"], "word": word})

    if tool_name == "lookup_lexicon":
        lemma = args.get("lemma", "")
        return MOCK_LEXICON.get(
            lemma,
            {
                "lemma": lemma,
                "definitions": ["Entry not found in mock lexicon."],
                "usage": "Connect with a live API key for full LSJ entries.",
            },
        )

    if tool_name == "scan_meter":
        line = args.get("line", "")
        return MOCK_SCANSION.get(
            line,
            {
                "line": line,
                "meter": "Dactylic Hexameter (mock)",
                "pattern": "— ∪∪ | — — | — ∪∪ | — ∪∪ | — ∪∪ | — —",
                "analysis": "Scansion unavailable in mock mode.",
            },
        )

    return {"error": f"Unknown tool: {tool_name}"}


# Hard timeout for the LLM tool calls (parse_greek, lookup_lexicon).
# scan_meter never reaches the LLM path — it uses the local scanner.
_LLM_TOOL_TIMEOUT_SECS = 5.0


async def execute_tool_live(
    tool_name: str, args: dict[str, Any], gemini_client: Any
) -> Any:
    """
    Execute a tool call.

    scan_meter  → always local deterministic scanner (meter.py), sub-millisecond.
    parse_greek → Gemini non-streaming call, thinking disabled, 5 s hard timeout.
    lookup_lexicon → same as parse_greek.
    """
    # ── scan_meter: fully local, no LLM ──────────────────────────────────────
    if tool_name == "scan_meter":
        from meter import scan_hexameter
        line = args.get("line", "")
        expected = args.get("expected_meter", "Dactylic Hexameter")
        t0 = time.perf_counter()
        result = scan_hexameter(line, expected)
        elapsed = round((time.perf_counter() - t0) * 1000, 2)
        print(f"[scan_meter] local scanner: {elapsed} ms (cached={elapsed < 0.1})")
        return result

    # ── parse_greek / lookup_lexicon: Gemini non-streaming ───────────────────
    try:
        word = args.get("word", args.get("lemma", ""))
        if tool_name == "parse_greek":
            prompt = (
                f"Return a JSON morphological analysis of the Ancient Greek word '{word}'. "
                "Include fields: word, lemma, transliteration, part_of_speech, tense (if verb), "
                "voice (if verb), mood (if verb), person (if verb), number, gender (if noun/adj), "
                "case (if noun/adj), definition, principal_parts (if verb), ipa (if known). "
                "Respond ONLY with valid JSON, no markdown."
            )
        elif tool_name == "lookup_lexicon":
            prompt = (
                f"Return a JSON lexicon entry for the Ancient Greek lemma '{word}' "
                "in LSJ style. Include: lemma, transliteration, part_of_speech, "
                "definitions (array), usage, key_refs (array). Respond ONLY with valid JSON."
            )
        else:
            return execute_tool_mock(tool_name, args)

        if gemini_client is None:
            return execute_tool_mock(tool_name, args)

        from google.genai import types as genai_types  # type: ignore[import]

        # Disable extended thinking (thinking_budget=0) — otherwise gemini-2.5-flash
        # can stall for 60-120 s before emitting a single token.
        try:
            thinking_config = genai_types.ThinkingConfig(thinking_budget=0)
            gen_config = genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                thinking_config=thinking_config,
            )
        except AttributeError:
            # Older SDK version without ThinkingConfig — fall back gracefully
            gen_config = genai_types.GenerateContentConfig(
                response_mime_type="application/json",
            )

        t0 = time.perf_counter()
        async with asyncio.timeout(_LLM_TOOL_TIMEOUT_SECS):
            response = await gemini_client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=gen_config,
            )
        elapsed = round((time.perf_counter() - t0) * 1000, 2)
        print(f"[{tool_name}] LLM call: {elapsed} ms")

        text = response.text or ""
        # Strip markdown fences the model may add despite response_mime_type
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            text = text.rsplit("```", 1)[0]
        return json.loads(text)

    except TimeoutError:
        print(f"[execute_tool_live] {tool_name} timed out after {_LLM_TOOL_TIMEOUT_SECS}s")
        result = execute_tool_mock(tool_name, args)
        result["_error"] = f"Tool timed out after {_LLM_TOOL_TIMEOUT_SECS}s"
        return result
    except Exception as exc:
        import traceback as tb
        tb.print_exc()
        print(f"[execute_tool_live] falling back to mock due to: {exc}")
        result = execute_tool_mock(tool_name, args)
        result["_error"] = str(exc)
        return result

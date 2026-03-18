"""Tests for preset passages."""

from presets import get_preset, list_presets, PRESET_PASSAGES


def test_get_known_preset():
    preset = get_preset("smoke_on_the_water")
    assert preset is not None
    assert preset["description"] == "Smoke on the Water — opening riff"
    assert preset["target_bpm"] == 112
    assert len(preset["target_notes"]) > 0


def test_get_unknown_preset():
    assert get_preset("nonexistent") is None


def test_list_presets_returns_summaries():
    summaries = list_presets()
    assert len(summaries) == len(PRESET_PASSAGES)
    for s in summaries:
        assert "id" in s
        assert "description" in s
        assert "target_bpm" in s
        assert "difficulty" in s
        # No note data in summary
        assert "target_notes" not in s


def test_all_presets_have_valid_notes():
    assert len(PRESET_PASSAGES) > 0, "No presets defined"
    for p in PRESET_PASSAGES:
        for note in p["target_notes"]:
            assert isinstance(note["onset_s"], (int, float))
            assert note["onset_s"] >= 0
            assert isinstance(note["midi"], int)
            assert 21 <= note["midi"] <= 108

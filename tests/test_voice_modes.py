"""Tests for the per-item voice-mode rotation in the rewriter."""
from collections import Counter

from src.pipeline.rewriter import VOICE_MODES, pick_voice_mode


def test_at_least_three_modes_defined():
    """We want at least 3 distinct voice modes for variety."""
    names = {m["name"] for m in VOICE_MODES}
    assert len(names) >= 3
    for m in VOICE_MODES:
        assert m["name"]
        assert m["description"]


def test_pick_voice_mode_is_deterministic():
    """Same item_id must always produce the same mode (so retries are stable)."""
    a = pick_voice_mode(42)
    b = pick_voice_mode(42)
    assert a["name"] == b["name"]


def test_different_ids_produce_a_distribution():
    """Across many item_ids, we should see most/all modes used.

    This is a statistical sanity check, not a strict equality - random.choice
    with a small number of buckets and 200 samples should hit every bucket
    with overwhelming probability.
    """
    seen = Counter(pick_voice_mode(i)["name"] for i in range(200))
    # All defined modes should appear at least once across 200 samples
    expected_modes = {m["name"] for m in VOICE_MODES}
    assert set(seen.keys()) == expected_modes
    # No single mode should monopolise (basic uniformity check)
    max_count = max(seen.values())
    assert max_count < 200 * 0.6, f"mode distribution too skewed: {seen}"


def test_pick_voice_mode_returns_full_record():
    mode = pick_voice_mode(1)
    assert "name" in mode
    assert "description" in mode
    assert isinstance(mode["description"], str)
    assert len(mode["description"]) > 20  # not empty / placeholder

"""
Tests for the pure-Python part of attention-region extraction
(ml/inference/aasist_wrapper.py's _bucket_node_salience_to_regions).

This is deliberately separated from the torch-tensor-touching code so it
can be verified directly with plain lists of numbers, without needing a
real model or torch installed.
"""
from ml.inference.aasist_wrapper import _bucket_node_salience_to_regions
from ml.preprocessing.audio import AASIST_NUM_SAMPLES, AASIST_SAMPLE_RATE

ANALYZED_WINDOW_SECONDS = AASIST_NUM_SAMPLES / AASIST_SAMPLE_RATE


def test_regions_are_chronological_and_span_the_analyzed_window():
    salience = [0.1] * 40
    regions = _bucket_node_salience_to_regions(salience, original_duration_seconds=10.0, num_regions=8)

    assert len(regions) == 8
    assert regions[0]["start"] == 0.0
    assert regions[-1]["end"] == round(ANALYZED_WINDOW_SECONDS, 2)
    for a, b in zip(regions, regions[1:]):
        assert a["end"] <= b["start"] + 0.01  # chronological, no overlap (allowing rounding)


def test_long_clip_regions_are_not_folded():
    """A clip longer than the analyzed window shouldn't have its region
    times folded — the window is just the clip's own first few seconds."""
    salience = [0.1] * 40
    salience[2] = 0.9
    regions = _bucket_node_salience_to_regions(salience, original_duration_seconds=10.0, num_regions=8)

    most_salient = max(regions, key=lambda r: r["salience"])
    assert most_salient["salience"] == 1.0
    assert most_salient["start"] == 0.0  # node 2 falls in the first bucket


def test_short_clip_regions_are_folded_into_original_bounds():
    """A clip shorter than the analyzed window gets tiled to fill it —
    every region's time must fold back into the original clip's own
    duration, not the longer analyzed window."""
    salience = [0.1] * 40
    salience[20] = 0.9
    original_duration = 1.0
    regions = _bucket_node_salience_to_regions(
        salience, original_duration_seconds=original_duration, num_regions=8
    )

    for r in regions:
        assert 0 <= r["start"] <= original_duration
        assert 0 <= r["end"] <= original_duration


def test_salience_is_normalized_0_to_1():
    salience = [0.2, 0.4, 0.6, 0.8] * 10
    regions = _bucket_node_salience_to_regions(salience, original_duration_seconds=10.0, num_regions=4)

    saliences = [r["salience"] for r in regions]
    assert min(saliences) == 0.0
    assert max(saliences) == 1.0


def test_uniform_salience_returns_midpoint_not_divide_by_zero():
    """If every node has identical salience (spread == 0), normalization
    shouldn't divide by zero — should fall back to a neutral 0.5."""
    salience = [0.5] * 40
    regions = _bucket_node_salience_to_regions(salience, original_duration_seconds=10.0, num_regions=8)

    assert all(r["salience"] == 0.5 for r in regions)


def test_empty_salience_returns_none():
    assert _bucket_node_salience_to_regions([], original_duration_seconds=10.0, num_regions=8) is None


def test_num_regions_capped_at_num_nodes():
    """Asking for more regions than there are nodes shouldn't crash or
    produce empty/duplicate regions."""
    salience = [0.1, 0.2, 0.3]
    regions = _bucket_node_salience_to_regions(salience, original_duration_seconds=10.0, num_regions=8)
    assert len(regions) == 3

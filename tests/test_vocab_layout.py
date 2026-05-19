"""Vocab layout + bin contract tests.

Locks the token ID table and quantization helpers per RESEARCH.md §"Vocab ID Layout"
and §"Duration Bin Scheme". Any change to these values requires bumping `schema_version`
in the pre-tokenized artifact format — downstream checkpoints depend on the integer
mapping being byte-stable.

Covers requirements TOK-01, TOK-02, TOK-03, TOK-04.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from apollo.tokenizer import (
    DURATION_EDGES,
    Vocab,
    decode_duration,
    decode_time_shift,
    decode_velocity,
    quantize_duration,
    quantize_time_shift,
    quantize_velocity,
)
from apollo.ingest import IngestError


def test_vocab_constants_exact_match():
    v = Vocab()
    assert v.PITCH_MIN == 36 and v.PITCH_MAX == 72 and v.N_PITCH == 37
    assert v.N_TIME == 32 and v.N_VELOCITY == 16 and v.N_DURATION == 24
    assert v.TIME_OFFSET == 0
    assert v.PITCH_OFFSET == 32
    assert v.VELOCITY_OFFSET == 69
    assert v.DURATION_OFFSET == 85
    assert v.BOS == 109 and v.EOS == 110 and v.SEP == 111
    assert v.VOCAB_SIZE == 256 and v.ACTIVE_VOCAB == 112


def test_vocab_ranges_contiguous_no_overlap():
    v = Vocab()
    # TIME range: 0..31 (32 slots), starting at TIME_OFFSET
    assert v.TIME_OFFSET == 0
    assert v.PITCH_OFFSET == v.TIME_OFFSET + v.N_TIME  # 0 + 32 = 32
    # PITCH range: 32..68 (37 slots)
    assert v.VELOCITY_OFFSET == v.PITCH_OFFSET + v.N_PITCH  # 32 + 37 = 69
    # VELOCITY range: 69..84 (16 slots)
    assert v.DURATION_OFFSET == v.VELOCITY_OFFSET + v.N_VELOCITY  # 69 + 16 = 85
    # DURATION range: 85..108 (24 slots) → BOS starts at 109
    assert v.BOS == v.DURATION_OFFSET + v.N_DURATION  # 85 + 24 = 109
    # Special tokens are last three of active vocab
    assert v.ACTIVE_VOCAB == v.SEP + 1
    # 144 reserved slots at the tail
    assert v.VOCAB_SIZE - v.ACTIVE_VOCAB == 144


def test_vocab_is_frozen():
    v = Vocab()
    with pytest.raises(dataclasses.FrozenInstanceError):
        v.PITCH_MIN = 0  # type: ignore[misc]


def test_special_tokens_unique_and_after_notes():
    v = Vocab()
    assert len({v.BOS, v.EOS, v.SEP}) == 3
    assert min(v.BOS, v.EOS, v.SEP) >= v.DURATION_OFFSET + v.N_DURATION


def test_duration_edges_shape_and_endpoints():
    assert len(DURATION_EDGES) == 25
    assert DURATION_EDGES[0] == pytest.approx(0.030)
    assert DURATION_EDGES[-1] == pytest.approx(1.500)
    # Monotonically increasing
    assert np.all(np.diff(DURATION_EDGES) > 0)


def test_quantize_duration_endpoints_and_clamping():
    assert quantize_duration(0.030) == 0
    assert quantize_duration(1.500) == 23
    # Clamp below
    assert quantize_duration(0.001) == 0
    # Clamp above
    assert quantize_duration(99.0) == 23


def test_decode_duration_in_bin_range():
    # Decoded value should sit inside the bin's edges
    for bin_i in range(24):
        d = decode_duration(bin_i)
        assert DURATION_EDGES[bin_i] <= d <= DURATION_EDGES[bin_i + 1]


def test_quantize_time_shift_basics():
    # 120 bpm: 32nd-note bin width = 0.03125 s
    assert quantize_time_shift(0.0) == 0
    assert quantize_time_shift(0.03125) == 1
    assert quantize_time_shift(0.03125 * 31) == 31


def test_quantize_time_shift_out_of_range_raises():
    with pytest.raises(ValueError):
        quantize_time_shift(99.0)
    with pytest.raises(ValueError):
        quantize_time_shift(-0.1)


def test_decode_time_shift_roundtrip():
    for bin_i in range(32):
        assert quantize_time_shift(decode_time_shift(bin_i)) == bin_i


def test_quantize_velocity_endpoints():
    assert quantize_velocity(1) == 0
    assert quantize_velocity(127) == 15
    # mid-range should be roughly in the middle
    assert quantize_velocity(64) in (7, 8)
    # clamping
    assert quantize_velocity(0) == 0
    assert quantize_velocity(200) == 15


def test_decode_velocity_in_midi_range():
    for bin_i in range(16):
        v = decode_velocity(bin_i)
        assert 1 <= v <= 127


def test_ingest_error_carries_path_and_reason():
    e = IngestError("data/pairs/003", "missing call.wav")
    assert e.pair_path == "data/pairs/003"
    assert e.reason == "missing call.wav"
    s = str(e)
    assert "data/pairs/003" in s
    assert "missing call.wav" in s

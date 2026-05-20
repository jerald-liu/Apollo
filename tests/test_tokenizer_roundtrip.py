"""TOK-05 round-trip tests for the symbolic tokenizer.

See .planning/phases/01-tokenizer-ingest/01-RESEARCH.md §"Round-Trip Test" for
tolerance derivation. Pitch must round-trip exactly (integer bins; any drift is
a bug). Velocity tolerance ±4 = half a velocity bin (16 bins over 1..127).
Onset tolerance 10 ms is tighter than half a time bin (~15 ms at 120 bpm); the
test inputs are chosen to fall on bin centers. Duration tolerance 19% matches
the log-bin Weber-fraction spacing (24 bins from 30 ms to 1.5 s).

Out-of-range pitch and over-window time_shift must abort with IngestError per
D-04 / D-16 — no silent clipping or wraparound.
"""

import pytest

from apollo.ingest import IngestError
from apollo.tokenizer import Note, Tokenizer, Vocab

PITCH_TOL = 0
VELOCITY_TOL = 4
ONSET_TOL_SEC = 0.010
DURATION_TOL_REL = 0.19


@pytest.fixture
def tokenizer():
    return Tokenizer(vocab=Vocab(), tempo_bpm=120.0)


def test_single_note_round_trip(tokenizer):
    """A single C4 quarter note at velocity 64 round-trips."""
    notes_in = [Note(pitch=60, velocity=64, start=0.0, end=0.5)]
    ids = tokenizer.encode(notes_in)
    assert len(ids) == 4
    notes_out = tokenizer.decode(ids)
    assert len(notes_out) == 1
    assert notes_out[0].pitch == 60
    assert abs(notes_out[0].velocity - 64) <= VELOCITY_TOL
    assert abs(notes_out[0].start - 0.0) <= ONSET_TOL_SEC
    expected_dur = 0.5
    actual_dur = notes_out[0].end - notes_out[0].start
    assert abs(actual_dur - expected_dur) / expected_dur <= DURATION_TOL_REL


def test_six_note_phrase(tokenizer):
    """A 6-note phrase across the pitch range round-trips."""
    notes_in = [
        Note(pitch=36, velocity=40,  start=0.000, end=0.125),  # C2
        Note(pitch=48, velocity=64,  start=0.125, end=0.250),  # C3
        Note(pitch=60, velocity=80,  start=0.375, end=0.500),  # C4
        Note(pitch=64, velocity=96,  start=0.500, end=0.625),  # E4
        Note(pitch=67, velocity=110, start=0.750, end=1.000),  # G4
        Note(pitch=72, velocity=120, start=1.000, end=1.500),  # C5
    ]
    ids = tokenizer.encode(notes_in)
    assert len(ids) == 4 * len(notes_in)
    # No leakage into special tokens / reserved range
    assert all(0 <= i < 109 for i in ids)
    notes_out = tokenizer.decode(ids)
    assert len(notes_out) == len(notes_in)
    for ni, no in zip(notes_in, notes_out):
        assert no.pitch == ni.pitch
        assert abs(no.velocity - ni.velocity) <= VELOCITY_TOL
        assert abs(no.start - ni.start) <= ONSET_TOL_SEC
        dur_in = ni.end - ni.start
        dur_out = no.end - no.start
        assert abs(dur_out - dur_in) / dur_in <= DURATION_TOL_REL


def test_pitch_out_of_range_aborts(tokenizer):
    notes = [Note(pitch=24, velocity=64, start=0.0, end=0.5)]  # below C2
    with pytest.raises(IngestError, match="outside"):
        tokenizer.encode(notes)


def test_pitch_above_range_aborts(tokenizer):
    notes = [Note(pitch=96, velocity=64, start=0.0, end=0.5)]  # above C5
    with pytest.raises(IngestError, match="outside"):
        tokenizer.encode(notes)


def test_time_shift_overflow_aborts(tokenizer):
    # 32 bins * (60/120)*2/32 = 1.0s; a 5s gap must abort
    notes = [
        Note(pitch=60, velocity=64, start=0.0, end=0.1),
        Note(pitch=62, velocity=64, start=5.0, end=5.1),
    ]
    with pytest.raises(IngestError, match="time_shift"):
        tokenizer.encode(notes)

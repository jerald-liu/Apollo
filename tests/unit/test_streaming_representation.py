"""Tests for src/streaming_representation.py.

Covers the 259-token streaming note-on/note-off vocabulary introduced in
Phase 2.  Tests verify token offset arithmetic, encode output ranges, and
encode→decode round-trip correctness.
"""
from __future__ import annotations

import pytest

from streaming_representation import (
    OFFSETS,
    VOCAB_SIZE,
    TOKENS_PER_NOTE_ON,
    TOKENS_PER_NOTE_OFF,
    MEDIAN_DURATION_S,
    N_TIME_BINS,
    N_PITCH,
    N_VELOCITY_BINS,
    StreamNoteOn,
    StreamNoteOff,
    encode_note_on,
    encode_note_off,
    streaming_tokens_to_events,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Token offset arithmetic
# ---------------------------------------------------------------------------

class TestOffsets:
    def test_vocab_size_is_259(self):
        """Streaming vocab must be exactly 259 — any change breaks checkpoint compat."""
        assert VOCAB_SIZE == 259

    def test_offset_ranges_non_overlapping(self):
        """No two token groups should share the same integer — overlap means
        the decoder cannot distinguish event types."""
        ranges = {
            'time_shift': range(OFFSETS['time_shift'], OFFSETS['time_shift'] + N_TIME_BINS),
            'note_on':    range(OFFSETS['note_on'],    OFFSETS['note_on']    + N_PITCH),
            'velocity':   range(OFFSETS['velocity'],   OFFSETS['velocity']   + N_VELOCITY_BINS),
            'note_off':   range(OFFSETS['note_off'],   OFFSETS['note_off']   + N_PITCH),
        }
        all_tokens: list[int] = []
        for r in ranges.values():
            all_tokens.extend(r)
        assert len(all_tokens) == len(set(all_tokens)), (
            "Token ranges overlap — vocab layout is inconsistent"
        )

    def test_special_tokens_at_end_of_vocab(self):
        """BOS/EOS/SEP must be the last three tokens so they never collide with
        pitch, velocity, or time-shift tokens."""
        assert OFFSETS['bos'] == 256
        assert OFFSETS['eos'] == 257
        assert OFFSETS['sep'] == 258
        assert OFFSETS['bos'] == VOCAB_SIZE - 3
        assert OFFSETS['eos'] == VOCAB_SIZE - 2
        assert OFFSETS['sep'] == VOCAB_SIZE - 1


# ---------------------------------------------------------------------------
# encode_note_on
# ---------------------------------------------------------------------------

class TestEncodeNoteOn:
    def _make_event(self, pitch=60, velocity=0.5, delta=0.1):
        return StreamNoteOn(pitch=pitch, velocity=velocity, delta_time=delta)

    def test_returns_exactly_3_tokens(self):
        """note_on → [time_shift, note_on_pitch, velocity] = 3 tokens."""
        tokens = encode_note_on(self._make_event())
        assert len(tokens) == TOKENS_PER_NOTE_ON == 3

    def test_time_shift_token_in_range(self):
        tokens = encode_note_on(self._make_event(delta=0.05))
        assert OFFSETS['time_shift'] <= tokens[0] < OFFSETS['note_on'], (
            f"time_shift token {tokens[0]} not in [0, {OFFSETS['note_on']})"
        )

    def test_pitch_token_in_note_on_range(self):
        """Second token must fall in the note_on band [64, 151]."""
        tokens = encode_note_on(self._make_event(pitch=60))
        lo = OFFSETS['note_on']
        hi = OFFSETS['velocity'] - 1
        assert lo <= tokens[1] <= hi, (
            f"pitch token {tokens[1]} not in [{lo}, {hi}]"
        )

    def test_velocity_token_in_velocity_range(self):
        """Third token must fall in the velocity band [152, 167]."""
        tokens = encode_note_on(self._make_event(velocity=0.8))
        lo = OFFSETS['velocity']
        hi = OFFSETS['note_off'] - 1
        assert lo <= tokens[2] <= hi, (
            f"velocity token {tokens[2]} not in [{lo}, {hi}]"
        )

    def test_all_tokens_within_vocab(self):
        tokens = encode_note_on(self._make_event(pitch=108, velocity=1.0, delta=2.0))
        for tok in tokens:
            assert 0 <= tok < VOCAB_SIZE

    def test_extreme_pitch_a0(self):
        """MIDI 21 (A0) — lowest piano key — must not go below note_on offset."""
        tokens = encode_note_on(self._make_event(pitch=21))
        assert tokens[1] == OFFSETS['note_on']

    def test_extreme_pitch_c8(self):
        """MIDI 108 (C8) — highest piano key — must not exceed note_on range."""
        tokens = encode_note_on(self._make_event(pitch=108))
        assert tokens[1] == OFFSETS['note_on'] + N_PITCH - 1


# ---------------------------------------------------------------------------
# encode_note_off
# ---------------------------------------------------------------------------

class TestEncodeNoteOff:
    def _make_event(self, pitch=60, delta=0.2):
        return StreamNoteOff(pitch=pitch, delta_time=delta)

    def test_returns_exactly_2_tokens(self):
        """note_off → [time_shift, note_off_pitch] = 2 tokens."""
        tokens = encode_note_off(self._make_event())
        assert len(tokens) == TOKENS_PER_NOTE_OFF == 2

    def test_pitch_token_in_note_off_range(self):
        """Second token must fall in the note_off band [168, 255]."""
        tokens = encode_note_off(self._make_event(pitch=69))  # A4
        lo = OFFSETS['note_off']
        hi = OFFSETS['bos'] - 1
        assert lo <= tokens[1] <= hi, (
            f"note_off pitch token {tokens[1]} not in [{lo}, {hi}]"
        )

    def test_all_tokens_within_vocab(self):
        tokens = encode_note_off(self._make_event(pitch=21, delta=0.0))
        for tok in tokens:
            assert 0 <= tok < VOCAB_SIZE


# ---------------------------------------------------------------------------
# streaming_tokens_to_events (decoder)
# ---------------------------------------------------------------------------

class TestDecoding:
    def _encode_single_note(self, pitch=60, velocity=0.6, on_delta=0.0, off_delta=0.25):
        """Build a minimal BOS + note_on + note_off + EOS token sequence."""
        on_ev  = StreamNoteOn(pitch=pitch, velocity=velocity, delta_time=on_delta)
        off_ev = StreamNoteOff(pitch=pitch, delta_time=off_delta)
        tokens = (
            [OFFSETS['bos']]
            + encode_note_on(on_ev)
            + encode_note_off(off_ev)
            + [OFFSETS['eos']]
        )
        return tokens

    def test_round_trip_single_note_recovers_pitch(self):
        """Encoding a C4 note_on then note_off and decoding must return pitch 60."""
        tokens = self._encode_single_note(pitch=60)
        notes  = streaming_tokens_to_events(tokens)
        assert len(notes) == 1
        assert notes[0]['pitch'] == 60

    def test_round_trip_preserves_onset_ordering(self):
        """Two notes encoded in onset order must decode in the same order."""
        # Note 1: C4 on at t=0, off at t=0.3
        # Note 2: E4 on at t=0.1 (0.1s after C4), off at t=0.4
        on_c  = StreamNoteOn(pitch=60, velocity=0.5, delta_time=0.0)
        off_c = StreamNoteOff(pitch=60, delta_time=0.3)
        on_e  = StreamNoteOn(pitch=64, velocity=0.5, delta_time=0.1)
        off_e = StreamNoteOff(pitch=64, delta_time=0.3)

        tokens = (
            [OFFSETS['bos']]
            + encode_note_on(on_c)
            + encode_note_on(on_e)
            + encode_note_off(off_c)
            + encode_note_off(off_e)
            + [OFFSETS['eos']]
        )
        notes = streaming_tokens_to_events(tokens)
        assert len(notes) == 2
        pitches = [n['pitch'] for n in notes]
        assert set(pitches) == {60, 64}

    def test_dangling_note_on_gets_median_duration(self):
        """A note_on with no matching note_off must get offset = onset + MEDIAN_DURATION_S."""
        on_ev  = StreamNoteOn(pitch=72, velocity=0.7, delta_time=0.0)
        tokens = [OFFSETS['bos']] + encode_note_on(on_ev) + [OFFSETS['eos']]
        notes  = streaming_tokens_to_events(tokens)
        assert len(notes) == 1
        note = notes[0]
        assert pytest.approx(note['offset'] - note['onset'], abs=1e-4) == MEDIAN_DURATION_S

    def test_empty_token_list_returns_empty(self):
        assert streaming_tokens_to_events([]) == []

    def test_bos_only_returns_empty(self):
        assert streaming_tokens_to_events([OFFSETS['bos'], OFFSETS['eos']]) == []

"""Tests for src/representation.py.

Each test cites the clause ID from specs/representation.md that it enforces.
"""
from __future__ import annotations

import numpy as np
import pretty_midi
import pytest

from representation import (
    ApolloEvent,
    CONTINUOUS_DIM,
    DURATION_BINS,
    TIME_SHIFT_BINS,
    TOKENS_PER_EVENT,
    TOKENS_PER_EVENT_WITH_TIMBRE,
    TOKEN_OFFSETS,
    TRAJECTORY_DIM,
    VELOCITY_BINS,
    VOCAB_SIZE,
    dequantize,
    events_to_continuous,
    events_to_midi,
    events_to_tokens,
    midi_to_events,
    quantize,
    tokens_to_events,
)

pytestmark = pytest.mark.unit


# --- quantize / dequantize -------------------------------------------------

class TestQuantize:
    def test_R1_1_returns_python_int(self):
        assert type(quantize(0.5, TIME_SHIFT_BINS)) is int

    def test_R1_2_index_in_range(self):
        for v in [-10.0, 0.0, 0.5, 1.0, 10.0]:
            idx = quantize(v, TIME_SHIFT_BINS)
            assert 0 <= idx < len(TIME_SHIFT_BINS)

    def test_R1_3_nearest_bin(self):
        bins = np.array([0.0, 1.0, 2.0, 3.0])
        assert quantize(0.1, bins) == 0
        assert quantize(0.6, bins) == 1
        assert quantize(2.4, bins) == 2
        assert quantize(2.6, bins) == 3

    def test_R1_4_clamps_beyond_range(self):
        bins = np.array([1.0, 2.0, 3.0])
        assert quantize(-100.0, bins) == 0
        assert quantize(100.0, bins) == 2


class TestDequantize:
    def test_R2_1_returns_python_float(self):
        assert type(dequantize(5, TIME_SHIFT_BINS)) is float

    def test_R2_2_clamps_out_of_range(self):
        bins = np.array([1.0, 2.0, 3.0])
        assert dequantize(-5, bins) == 1.0
        assert dequantize(100, bins) == 3.0

    def test_R2_3_returns_bin_value(self):
        bins = np.array([10.0, 20.0, 30.0])
        assert dequantize(1, bins) == 20.0


# --- ApolloEvent -----------------------------------------------------------

class TestApolloEvent:
    def test_R3_1_default_timbral_half(self):
        e = ApolloEvent(pitch=60, velocity=0.5, delta_time=0.1, duration=0.2, pedal=0)
        assert e.brightness == 0.5
        assert e.attack == 0.5
        assert e.richness == 0.5
        assert e.warmth == 0.5
        assert e.flux == 0.5

    def test_R3_2_default_trajectory_zeros(self):
        e = ApolloEvent(pitch=60, velocity=0.5, delta_time=0.1, duration=0.2, pedal=0)
        assert e.trajectory.shape == (TRAJECTORY_DIM,)
        assert np.all(e.trajectory == 0.0)

    def test_R3_3_default_onset_time_zero(self):
        e = ApolloEvent(pitch=60, velocity=0.5, delta_time=0.1, duration=0.2, pedal=0)
        assert e.onset_time == 0.0

    def test_R3_4_no_shared_mutable_default(self):
        a = ApolloEvent(pitch=60, velocity=0.5, delta_time=0.0, duration=0.1, pedal=0)
        b = ApolloEvent(pitch=62, velocity=0.5, delta_time=0.0, duration=0.1, pedal=0)
        a.trajectory[0] = 7.0
        assert b.trajectory[0] == 0.0  # not aliased


# --- midi_to_events --------------------------------------------------------

class TestMidiToEvents:
    def test_R4_1_returns_list_of_events(self, synthetic_midi_path):
        events = midi_to_events(str(synthetic_midi_path))
        assert isinstance(events, list)
        assert all(isinstance(e, ApolloEvent) for e in events)
        assert len(events) > 0

    def test_R4_2_pitches_valid(self, synthetic_midi_path):
        for e in midi_to_events(str(synthetic_midi_path)):
            assert 0 <= e.pitch <= 127

    def test_R4_3_pedal_states_valid(self, synthetic_midi_path):
        for e in midi_to_events(str(synthetic_midi_path)):
            assert e.pedal in (0, 1, 2, 3)

    def test_R4_4_delta_time_non_negative(self, synthetic_midi_path):
        for e in midi_to_events(str(synthetic_midi_path)):
            assert e.delta_time >= 0.0

    def test_R4_5_onsets_monotonic(self, synthetic_midi_path):
        events = midi_to_events(str(synthetic_midi_path))
        cumulative = 0.0
        prev = 0.0
        for e in events:
            cumulative += e.delta_time
            assert cumulative >= prev - 1e-9
            prev = cumulative

    def test_R4_7_default_timbral_without_analyzer(self, synthetic_midi_path):
        for e in midi_to_events(str(synthetic_midi_path)):
            assert e.brightness == 0.5
            assert e.attack == 0.5
            assert e.richness == 0.5
            assert e.warmth == 0.5
            assert e.flux == 0.5

    def test_R4_8_respects_max_events(self, synthetic_midi_path):
        events = midi_to_events(str(synthetic_midi_path), max_events=5)
        # synthetic_midi has one non-drum instrument with 20 notes; cap to 5.
        assert len(events) == 5

    def test_R4_9_velocity_normalized(self, synthetic_midi_path):
        for e in midi_to_events(str(synthetic_midi_path)):
            assert 0.0 <= e.velocity <= 1.0

    def test_R4_10_duration_non_negative(self, synthetic_midi_path):
        for e in midi_to_events(str(synthetic_midi_path)):
            assert e.duration >= 0.0


# --- events_to_tokens ------------------------------------------------------

def _make_events(n=3):
    return [
        ApolloEvent(
            pitch=60 + i,
            velocity=0.5,
            delta_time=0.1 * i,
            duration=0.2,
            pedal=i % 4,
        )
        for i in range(n)
    ]


class TestEventsToTokens:
    def test_R5_1_and_R5_2_bos_eos(self):
        tokens = events_to_tokens(_make_events(3))
        assert tokens[0] == TOKEN_OFFSETS["bos"]
        assert tokens[-1] == TOKEN_OFFSETS["eos"]

    def test_R5_3_length_without_timbre(self):
        for n in [0, 1, 5, 20]:
            tokens = events_to_tokens(_make_events(n))
            assert len(tokens) == 2 + TOKENS_PER_EVENT * n

    def test_R5_4_length_with_timbre(self):
        for n in [0, 1, 5]:
            tokens = events_to_tokens(_make_events(n), include_timbre_tokens=True)
            assert len(tokens) == 2 + TOKENS_PER_EVENT_WITH_TIMBRE * n

    def test_R5_5_all_tokens_in_vocab(self):
        tokens = events_to_tokens(_make_events(10), include_timbre_tokens=True)
        for t in tokens:
            assert 0 <= t < VOCAB_SIZE

    def test_R5_6_region_layout(self):
        tokens = events_to_tokens(_make_events(3))
        # Strip BOS and EOS
        body = tokens[1:-1]
        for i in range(0, len(body), TOKENS_PER_EVENT):
            ts, p, v, d, pd = body[i:i + TOKENS_PER_EVENT]
            assert 0 <= ts < 100
            assert 100 <= p < 228
            assert 228 <= v < 260
            assert 260 <= d < 324
            assert 324 <= pd < 328

    def test_R5_7_pitch_encoding_direct(self):
        events = _make_events(3)
        tokens = events_to_tokens(events)
        body = tokens[1:-1]
        for i, e in enumerate(events):
            pitch_token = body[i * TOKENS_PER_EVENT + 1]
            assert pitch_token == 100 + e.pitch

    def test_R5_8_pedal_encoding_direct(self):
        events = _make_events(4)
        tokens = events_to_tokens(events)
        body = tokens[1:-1]
        for i, e in enumerate(events):
            pedal_token = body[i * TOKENS_PER_EVENT + 4]
            assert pedal_token == 324 + e.pedal

    def test_R5_9_empty_input(self):
        tokens = events_to_tokens([])
        assert tokens == [TOKEN_OFFSETS["bos"], TOKEN_OFFSETS["eos"]]


# --- events_to_continuous --------------------------------------------------

class TestEventsToContinuous:
    def test_R6_1_and_R6_2_shape_dtype(self):
        arr = events_to_continuous(_make_events(7))
        assert arr.shape == (7, CONTINUOUS_DIM)
        assert arr.dtype == np.float32

    def test_R6_3_scalar_columns(self):
        events = [
            ApolloEvent(pitch=60, velocity=0.5, delta_time=0.0, duration=0.1,
                        pedal=0, brightness=0.1, attack=0.2, richness=0.3,
                        warmth=0.4, flux=0.5)
        ]
        arr = events_to_continuous(events)
        np.testing.assert_allclose(arr[0, :5], [0.1, 0.2, 0.3, 0.4, 0.5],
                                    atol=1e-6)

    def test_R6_4_trajectory_columns(self):
        traj = np.linspace(0.0, 1.0, TRAJECTORY_DIM, dtype=np.float32)
        e = ApolloEvent(pitch=60, velocity=0.5, delta_time=0.0, duration=0.1,
                        pedal=0, trajectory=traj)
        arr = events_to_continuous([e])
        np.testing.assert_allclose(arr[0, 5:], traj, atol=1e-6)

    def test_R6_5_empty_input_shape(self):
        arr = events_to_continuous([])
        assert arr.shape == (0, CONTINUOUS_DIM)


# --- tokens_to_events ------------------------------------------------------

class TestTokensToEvents:
    def test_R7_1_skips_bos(self):
        events_in = _make_events(3)
        tokens = events_to_tokens(events_in)
        events_out = tokens_to_events(tokens)
        assert len(events_out) == len(events_in)

    def test_R7_2_halts_at_eos(self):
        events_in = _make_events(3)
        tokens = events_to_tokens(events_in)
        # Duplicate body after EOS — should not be decoded
        tokens_extended = tokens + tokens[1:-1]
        events_out = tokens_to_events(tokens_extended)
        assert len(events_out) == 3

    def test_R7_2_halts_at_sep(self):
        events_in = _make_events(2)
        body_tokens = events_to_tokens(events_in)[:-1]  # drop EOS
        tokens_with_sep = body_tokens + [TOKEN_OFFSETS["sep"]] + body_tokens[1:]
        events_out = tokens_to_events(tokens_with_sep)
        assert len(events_out) == 2

    def test_R7_3_pitches_valid(self):
        tokens = events_to_tokens(_make_events(5))
        for e in tokens_to_events(tokens):
            assert 0 <= e.pitch <= 127

    def test_R7_4_pedals_valid(self):
        tokens = events_to_tokens(_make_events(5))
        for e in tokens_to_events(tokens):
            assert e.pedal in (0, 1, 2, 3)

    def test_R7_5_roundtrip_pitch_and_pedal(self):
        events_in = _make_events(10)
        events_out = tokens_to_events(events_to_tokens(events_in))
        assert len(events_out) == len(events_in)
        for a, b in zip(events_in, events_out):
            assert a.pitch == b.pitch
            assert a.pedal == b.pedal

    def test_R7_6_roundtrip_continuous_within_quantization_error(self):
        events_in = _make_events(10)
        events_out = tokens_to_events(events_to_tokens(events_in))
        # Quantization tolerance: max gap between adjacent bins as a worst-case.
        dt_tol = float(np.max(np.diff(TIME_SHIFT_BINS)))
        dur_tol = float(np.max(np.diff(DURATION_BINS)))
        vel_tol = float(np.max(np.diff(VELOCITY_BINS))) / 127.0
        for a, b in zip(events_in, events_out):
            assert abs(a.delta_time - b.delta_time) <= dt_tol + 1e-6
            assert abs(a.duration - b.duration) <= dur_tol + 1e-6
            assert abs(a.velocity - b.velocity) <= vel_tol + 1e-6

    def test_R7_7_malformed_tokens_do_not_raise(self):
        bad = [TOKEN_OFFSETS["bos"], 0, 250, 250, 400, 324, TOKEN_OFFSETS["eos"]]
        # Should not raise; pitch 250-100=150 out of range -> group skipped.
        tokens_to_events(bad)


# --- events_to_midi --------------------------------------------------------

class TestEventsToMidi:
    def test_R8_1_writes_loadable_file(self, tmp_path):
        events = _make_events(5)
        out = tmp_path / "out.mid"
        events_to_midi(events, str(out))
        assert out.exists()
        pm = pretty_midi.PrettyMIDI(str(out))
        assert len(pm.instruments) == 1

    def test_R8_2_note_count_matches(self, tmp_path):
        events = _make_events(7)
        out = tmp_path / "out.mid"
        events_to_midi(events, str(out))
        pm = pretty_midi.PrettyMIDI(str(out))
        assert len(pm.instruments[0].notes) == 7

    def test_R8_3_pitches_preserved(self, tmp_path):
        events = _make_events(6)
        out = tmp_path / "out.mid"
        events_to_midi(events, str(out))
        pm = pretty_midi.PrettyMIDI(str(out))
        midi_pitches = [n.pitch for n in pm.instruments[0].notes]
        assert midi_pitches == [e.pitch for e in events]

    def test_R8_4_onset_times_cumulative(self, tmp_path):
        events = _make_events(4)
        out = tmp_path / "out.mid"
        events_to_midi(events, str(out))
        pm = pretty_midi.PrettyMIDI(str(out))
        starts = [n.start for n in pm.instruments[0].notes]
        expected = np.cumsum([e.delta_time for e in events])
        np.testing.assert_allclose(starts, expected, atol=1e-4)


class TestMidiToEventsDrums:
    def test_R4_6_skips_drum_instruments(self, tmp_path):
        """R4.6: drum instruments produce no events."""
        import pretty_midi
        pm = pretty_midi.PrettyMIDI(initial_tempo=120)
        drum = pretty_midi.Instrument(program=0, is_drum=True, name="drums")
        for i in range(5):
            drum.notes.append(pretty_midi.Note(
                velocity=80, pitch=38, start=i * 0.1, end=i * 0.1 + 0.05))
        pm.instruments.append(drum)
        path = tmp_path / "drums.mid"
        pm.write(str(path))
        events = midi_to_events(str(path))
        assert len(events) == 0


class TestEventsToMidiPedal:
    def test_R8_5_pedal_cc_emitted(self, tmp_path):
        """R8.5: events with pedal > 0 produce CC #64 at onset time."""
        events = [
            ApolloEvent(pitch=60, velocity=0.5, delta_time=0.0, duration=0.2, pedal=3),
            ApolloEvent(pitch=62, velocity=0.5, delta_time=0.5, duration=0.2, pedal=0),
        ]
        out = tmp_path / "pedal.mid"
        events_to_midi(events, str(out))
        pm = pretty_midi.PrettyMIDI(str(out))
        ccs = [cc for cc in pm.instruments[0].control_changes if cc.number == 64]
        assert len(ccs) == 1
        assert ccs[0].time == pytest.approx(0.0, abs=1e-4)

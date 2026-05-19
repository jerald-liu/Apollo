"""Integration tests for scripts/preprocess.py.

Drives the MIDI->tokens->windows pipeline with synthetic MIDI. No MAESTRO
dataset required.

Each test cites the clause ID from specs/preprocess.md it enforces.
"""
from __future__ import annotations

import numpy as np
import pytest

from preprocess import create_training_windows, process_file
from representation import VOCAB_SIZE

pytestmark = pytest.mark.integration


# --- process_file ---------------------------------------------------------

class TestProcessFile:
    def test_P1_1_returns_none_when_too_few_events(self, tmp_path):
        # Create a MIDI with only 5 notes (below the 10-event floor).
        import pretty_midi
        pm = pretty_midi.PrettyMIDI(initial_tempo=120)
        inst = pretty_midi.Instrument(program=0)
        for i in range(5):
            inst.notes.append(pretty_midi.Note(
                velocity=80, pitch=60 + i, start=i * 0.1, end=i * 0.1 + 0.05
            ))
        pm.instruments.append(inst)
        midi_path = tmp_path / "short.mid"
        pm.write(str(midi_path))

        result = process_file((str(midi_path), None, False, 2048))
        assert result is None

    def test_P1_2_error_dict_on_corrupt_file(self, corrupt_midi_path):
        result = process_file((str(corrupt_midi_path), None, False, 2048))
        assert result is not None
        assert "error" in result
        assert "file" in result

    def test_P1_3_success_keys(self, synthetic_midi_path):
        result = process_file((str(synthetic_midi_path), None, False, 2048))
        assert result is not None
        assert "error" not in result
        for k in ("tokens", "continuous", "n_events", "n_tokens"):
            assert k in result

    def test_P1_4_n_tokens_matches_tokens(self, synthetic_midi_path):
        result = process_file((str(synthetic_midi_path), None, False, 2048))
        assert result["n_tokens"] == len(result["tokens"])

    def test_P1_5_event_floor(self, synthetic_midi_path):
        result = process_file((str(synthetic_midi_path), None, False, 2048))
        assert result["n_events"] >= 10

    def test_P1_6_continuous_none_without_spectral(self, synthetic_midi_path):
        result = process_file((str(synthetic_midi_path), None, False, 2048))
        assert result["continuous"] is None

    def test_P1_7_tokens_in_vocab(self, synthetic_midi_path):
        result = process_file((str(synthetic_midi_path), None, False, 2048))
        for t in result["tokens"]:
            assert 0 <= t < VOCAB_SIZE


# --- create_training_windows ----------------------------------------------

def _toy_tokens(length=200):
    """A token sequence that stays inside vocab (BOS + 5-token events + EOS)."""
    toks = [377]  # BOS
    for i in range((length - 2) // 5):
        toks += [i % 100, 100 + (i % 128), 228 + (i % 32), 260 + (i % 64), 324 + (i % 4)]
    toks.append(378)  # EOS
    return toks


class TestCreateTrainingWindows:
    def test_P2_1_returns_tuple(self):
        tokens = _toy_tokens(200)
        tok_arr, cont_arr, _, _ = create_training_windows([tokens], None, 50, 25)
        assert isinstance(tok_arr, np.ndarray)
        assert cont_arr is None

    def test_P2_2_shape(self):
        tokens = _toy_tokens(200)
        seq_len = 50
        tok_arr, _, _, _ = create_training_windows([tokens], None, seq_len, 25)
        assert tok_arr.ndim == 2
        assert tok_arr.shape[1] == seq_len + 1

    def test_P2_3_dtype(self):
        tokens = _toy_tokens(200)
        tok_arr, _, _, _ = create_training_windows([tokens], None, 50, 25)
        assert tok_arr.dtype == np.int32

    def test_P2_4_tokens_in_vocab(self):
        tokens = _toy_tokens(200)
        tok_arr, _, _, _ = create_training_windows([tokens], None, 50, 25)
        assert tok_arr.min() >= 0
        assert tok_arr.max() < VOCAB_SIZE

    def test_P2_5_window_count(self):
        """Window count matches range(0, L - seq_len, stride)."""
        tokens = _toy_tokens(200)
        seq_len, stride = 50, 25
        tok_arr, _, _, _ = create_training_windows([tokens], None, seq_len, stride)
        expected = len(range(0, len(tokens) - seq_len, stride))
        assert tok_arr.shape[0] == expected

    def test_P2_6_continuous_none_passthrough(self):
        tokens = _toy_tokens(200)
        _, cont_arr, _, _ = create_training_windows([tokens], None, 50, 25)
        assert cont_arr is None

    def test_P2_7_continuous_dtype_and_alignment(self):
        tokens = _toy_tokens(200)
        n_events_approx = len(tokens) // 5 + 5
        continuous = [np.zeros((n_events_approx, 21), dtype=np.float32)]
        tok_arr, cont_arr, _, _ = create_training_windows(
            [tokens], continuous, 50, 25
        )
        assert cont_arr is not None
        assert cont_arr.dtype == np.float32
        assert cont_arr.shape[0] == tok_arr.shape[0]


# --- end-to-end -----------------------------------------------------------

class TestEndToEnd:
    def test_P3_1_synthetic_midi_to_windows(self, synthetic_midi_path):
        result = process_file((str(synthetic_midi_path), None, False, 2048))
        assert result is not None and "error" not in result

        # Synthetic MIDI has 20 notes → 2 + 20*5 = 102 tokens.
        # Pick a seq_len smaller than that.
        seq_len = 40
        tok_arr, _, _, _ = create_training_windows([result["tokens"]], None, seq_len, 20)
        assert tok_arr.shape[0] >= 1
        assert tok_arr.shape[1] == seq_len + 1

    def test_P3_2_mixed_valid_and_corrupt(self, synthetic_midi_path, corrupt_midi_path):
        r_ok = process_file((str(synthetic_midi_path), None, False, 2048))
        r_bad = process_file((str(corrupt_midi_path), None, False, 2048))
        assert r_ok is not None and "error" not in r_ok
        assert r_bad is not None and "error" in r_bad

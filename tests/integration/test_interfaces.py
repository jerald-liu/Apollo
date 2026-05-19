"""Interface contract tests.

Each test enforces a clause from specs/interfaces.md, running both sides of a
module boundary together. A failure here means the seam is broken, not just one
module in isolation.
"""
from __future__ import annotations

import numpy as np
import pytest
import torch

from representation import (
    CONTINUOUS_DIM,
    TOKEN_OFFSETS,
    TOKENS_PER_EVENT,
    TRAJECTORY_DIM,
    VOCAB_SIZE,
    ApolloEvent,
    events_to_continuous,
    events_to_tokens,
)
from model import ApolloModel, SpectralEncoder
from spectral import SpectralAnalyzer, SpectralTrajectory
from preprocess import create_training_windows, process_file

pytestmark = pytest.mark.integration

TINY = dict(vocab_size=380, d_model=32, nhead=2, num_layers=2,
            max_seq_len=64, user_embed_dim=0, spectral_dim=21,
            n_timbre_outputs=5, dropout=0.0)


def _make_events(n=5):
    return [ApolloEvent(pitch=60+i, velocity=0.5, delta_time=0.1,
                        duration=0.2, pedal=0) for i in range(n)]


# --- I:R→M ----------------------------------------------------------------

class TestRepresentationToModel:
    def test_IR_M_1_tokens_in_embedding_range(self):
        """IR→M.1: all tokens from events_to_tokens are valid embedding indices."""
        tokens = events_to_tokens(_make_events(10), include_timbre_tokens=True)
        model = ApolloModel(**TINY)
        t = torch.tensor(tokens).unsqueeze(0)[:, :TINY["max_seq_len"]]
        # Would raise IndexError if any token >= vocab_size
        out = model(t)
        assert out["logits"].shape[-1] == VOCAB_SIZE

    def test_IR_M_2_continuous_dim_matches_spectral_encoder(self):
        """IR→M.2: CONTINUOUS_DIM == spectral_dim the encoder was built with."""
        assert CONTINUOUS_DIM == 21
        enc = SpectralEncoder(spectral_dim=CONTINUOUS_DIM, d_model=32)
        cont = events_to_continuous(_make_events(4))  # (4, 21)
        t = torch.tensor(cont).unsqueeze(0)           # (1, 4, 21)
        out = enc(t)
        assert out.shape == (1, 4, 32)

    def test_IR_M_3_spectral_alignment(self):
        """IR→M.3: token count T == 2 + N*TOKENS_PER_EVENT; expansion aligns."""
        events = _make_events(4)
        tokens = events_to_tokens(events)
        cont = events_to_continuous(events)            # (4, 21)
        T = len(tokens)
        assert T == 2 + len(events) * TOKENS_PER_EVENT

        model = ApolloModel(**TINY)
        t = torch.tensor(tokens).unsqueeze(0)[:, :TINY["max_seq_len"]]
        s = torch.tensor(cont).unsqueeze(0)           # (1, 4, 21)
        # Should not raise; spectral expansion must handle T correctly
        out = model(t, spectral_features=s, tokens_per_event=TOKENS_PER_EVENT)
        assert out["logits"].shape[1] == t.shape[1]

    def test_IR_M_4_bos_eos_positions(self):
        """IR→M.4: BOS at index 0, EOS at last index only."""
        tokens = events_to_tokens(_make_events(3))
        assert tokens[0] == TOKEN_OFFSETS["bos"]
        assert tokens[-1] == TOKEN_OFFSETS["eos"]
        # BOS/EOS must not appear in the middle
        assert TOKEN_OFFSETS["bos"] not in tokens[1:-1]
        assert TOKEN_OFFSETS["eos"] not in tokens[1:-1]


# --- I:R→P ----------------------------------------------------------------

class TestRepresentationToPreprocess:
    def test_IR_P_1_n_tokens_matches_list(self, synthetic_midi_path):
        """IR→P.1: process_file n_tokens == len(tokens)."""
        r = process_file((str(synthetic_midi_path), None, False, 2048))
        assert r is not None and "error" not in r
        assert r["n_tokens"] == len(r["tokens"])

    def test_IR_P_2_all_tokens_valid_after_windowing(self, synthetic_midi_path):
        """IR→P.2: tokens survive windowing with all values in vocab range."""
        r = process_file((str(synthetic_midi_path), None, False, 2048))
        seq_len = 20
        tok_arr, _, _, _ = create_training_windows([r["tokens"]], None, seq_len, 10)
        assert tok_arr.min() >= 0
        assert tok_arr.max() < VOCAB_SIZE

    def test_IR_P_3_window_shape_and_dtype(self, synthetic_midi_path):
        """IR→P.3: windows are int32 with shape (N, seq_len+1)."""
        r = process_file((str(synthetic_midi_path), None, False, 2048))
        seq_len = 20
        tok_arr, _, _, _ = create_training_windows([r["tokens"]], None, seq_len, 10)
        assert tok_arr.dtype == np.int32
        assert tok_arr.shape[1] == seq_len + 1
        # Targets are window[:, 1:], inputs window[:, :-1] — must both be valid
        inputs = tok_arr[:, :-1]
        targets = tok_arr[:, 1:]
        assert inputs.shape == targets.shape == (tok_arr.shape[0], seq_len)


# --- I:S→R ----------------------------------------------------------------

class TestSpectralToRepresentation:
    def test_IS_R_1_normalized_profile_fields_in_unit_range(self, synthetic_audio_arrays):
        """IS→R.1: normalized NoteSpectralProfile fields stay in [0, 1]."""
        analyzer = SpectralAnalyzer()
        onset = float(synthetic_audio_arrays["times"][5])
        offset = float(synthetic_audio_arrays["times"][15])
        profile = analyzer.get_note_profile(synthetic_audio_arrays, onset, offset)

        # Build stats from a small set of profiles
        profiles = [analyzer.get_note_profile(synthetic_audio_arrays,
                    float(synthetic_audio_arrays["times"][i]),
                    float(synthetic_audio_arrays["times"][i+10]))
                    for i in range(0, 50, 10)]
        stats = analyzer.compute_normalization_stats(profiles)
        norm = analyzer.normalize_profile(profile, stats)

        for field in ("brightness", "attack", "richness", "warmth", "flux"):
            v = getattr(norm, field)
            assert 0.0 <= v <= 1.0, f"{field}={v} out of [0,1]"

    def test_IS_R_2_trajectory_dim_matches_event_field(self, synthetic_audio_arrays):
        """IS→R.2: to_embedding(dim=TRAJECTORY_DIM) matches ApolloEvent.trajectory shape."""
        traj = SpectralTrajectory(synthetic_audio_arrays, window_sec=0.5, hop_sec=0.1)
        emb = traj.to_embedding(1.0, dim=TRAJECTORY_DIM)
        assert emb.shape == (TRAJECTORY_DIM,)
        e = ApolloEvent(pitch=60, velocity=0.5, delta_time=0.0,
                        duration=0.2, pedal=0, trajectory=emb)
        assert e.trajectory.shape == (TRAJECTORY_DIM,)

    def test_IS_R_3_continuous_trajectory_columns(self, synthetic_audio_arrays):
        """IS→R.3: events_to_continuous reads columns [5:5+TRAJECTORY_DIM]."""
        traj = SpectralTrajectory(synthetic_audio_arrays, window_sec=0.5, hop_sec=0.1)
        emb = traj.to_embedding(1.0, dim=TRAJECTORY_DIM)
        e = ApolloEvent(pitch=60, velocity=0.5, delta_time=0.0,
                        duration=0.2, pedal=0, trajectory=emb)
        cont = events_to_continuous([e])
        np.testing.assert_allclose(cont[0, 5:5+TRAJECTORY_DIM], emb, atol=1e-6)


# --- I:M→G ----------------------------------------------------------------

class TestModelForwardToGenerate:
    def test_IM_G_1_forward_always_has_logits(self):
        """IM→G.1: forward always returns 'logits'; generate can always index it."""
        model = ApolloModel(**TINY)
        model.eval()
        tokens = torch.randint(0, 380, (1, 10))
        out = model(tokens)
        assert "logits" in out
        assert out["logits"].shape == (1, 10, 380)
        # Simulate what generate does at each step
        next_logits = out["logits"][:, -1, :]
        assert next_logits.shape == (1, 380)

    def test_IM_G_2_timbre_key_present_when_head_exists(self):
        """IM→G.2: forward returns 'timbre' when timbre_head is not None."""
        model = ApolloModel(**TINY)
        model.eval()
        tokens = torch.randint(0, 380, (1, 10))
        out = model(tokens)
        assert "timbre" in out
        # Simulate generate's per-step append
        step_timbre = out["timbre"][:, -1, :]
        assert step_timbre.shape == (1, TINY["n_timbre_outputs"])

    def test_IM_G_3_eos_index_consistent(self):
        """IM→G.3: EOS token in representation matches hardcoded index in generate."""
        # generate halts on token == 378 (hardcoded in model.py line 261)
        assert TOKEN_OFFSETS["eos"] == 378

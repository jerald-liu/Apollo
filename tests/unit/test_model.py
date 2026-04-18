"""Tests for src/model.py.

All model tests run on CPU with a tiny config to keep CI fast.
Each test cites the clause ID from specs/model.md it enforces.
"""
from __future__ import annotations

import pytest
import torch

from model import ApolloModel, SpectralEncoder, TimbrePredictor

pytestmark = pytest.mark.unit


# Tiny config for fast CPU tests
TINY_CFG = dict(
    vocab_size=380,
    d_model=32,
    nhead=2,
    num_layers=2,
    max_seq_len=64,
    user_embed_dim=8,
    spectral_dim=21,
    n_timbre_outputs=5,
    dropout=0.0,
)


@pytest.fixture
def tiny_model():
    torch.manual_seed(0)
    m = ApolloModel(**TINY_CFG)
    m.eval()
    return m


# --- SpectralEncoder ------------------------------------------------------

class TestSpectralEncoder:
    def test_M1_1_shape(self):
        enc = SpectralEncoder(spectral_dim=21, d_model=32)
        x = torch.randn(2, 5, 21)
        out = enc(x)
        assert out.shape == (2, 5, 32)

    def test_M1_2_arbitrary_batch_and_time(self):
        enc = SpectralEncoder(spectral_dim=21, d_model=32)
        for B, T in [(1, 1), (3, 10), (1, 50)]:
            out = enc(torch.randn(B, T, 21))
            assert out.shape == (B, T, 32)

    def test_M1_4_finite(self):
        enc = SpectralEncoder(spectral_dim=21, d_model=32)
        out = enc(torch.randn(2, 5, 21))
        assert torch.isfinite(out).all()


# --- TimbrePredictor -------------------------------------------------------

class TestTimbrePredictor:
    def test_M2_1_shape(self):
        pred = TimbrePredictor(d_model=32, n_descriptors=5)
        h = torch.randn(2, 7, 32)
        out = pred(h)
        assert out.shape == (2, 7, 5)

    def test_M2_2_sigmoid_range(self):
        pred = TimbrePredictor(d_model=32, n_descriptors=5)
        # Extreme input → sigmoid saturates inside [0, 1]
        out = pred(torch.randn(2, 7, 32) * 1000)
        assert out.min() >= 0.0
        assert out.max() <= 1.0


# --- ApolloModel construction --------------------------------------------

class TestApolloModelInit:
    def test_M3_1_default_config(self):
        m = ApolloModel()
        assert m.vocab_size == 380
        assert m.d_model == 256
        assert m.max_seq_len == 1024

    def test_M3_2_spectral_encoder_optional(self):
        m_with = ApolloModel(**{**TINY_CFG, "spectral_dim": 21})
        m_without = ApolloModel(**{**TINY_CFG, "spectral_dim": 0})
        assert m_with.spectral_encoder is not None
        assert m_without.spectral_encoder is None

    def test_M3_3_timbre_head_optional(self):
        m_with = ApolloModel(**{**TINY_CFG, "n_timbre_outputs": 5})
        m_without = ApolloModel(**{**TINY_CFG, "n_timbre_outputs": 0})
        assert m_with.timbre_head is not None
        assert m_without.timbre_head is None

    def test_M3_4_user_proj_optional(self):
        m_with = ApolloModel(**{**TINY_CFG, "user_embed_dim": 16})
        m_without = ApolloModel(**{**TINY_CFG, "user_embed_dim": 0})
        assert m_with.user_proj is not None
        assert m_without.user_proj is None

    def test_M3_5_default_param_count(self):
        m = ApolloModel()
        n_params = sum(p.numel() for p in m.parameters())
        assert n_params < 20_000_000


# --- ApolloModel.forward --------------------------------------------------

class TestApolloModelForward:
    def test_M4_2_logits_shape(self, tiny_model):
        B, T = 2, 20
        tokens = torch.randint(0, TINY_CFG["vocab_size"], (B, T))
        out = tiny_model(tokens)
        assert "logits" in out
        assert out["logits"].shape == (B, T, TINY_CFG["vocab_size"])

    def test_M4_3_timbre_shape(self, tiny_model):
        B, T = 2, 20
        tokens = torch.randint(0, TINY_CFG["vocab_size"], (B, T))
        out = tiny_model(tokens)
        assert "timbre" in out
        assert out["timbre"].shape == (B, T, TINY_CFG["n_timbre_outputs"])
        assert out["timbre"].min() >= 0.0
        assert out["timbre"].max() <= 1.0

    def test_M4_4_no_spectral(self, tiny_model):
        tokens = torch.randint(0, TINY_CFG["vocab_size"], (1, 10))
        out = tiny_model(tokens, spectral_features=None)
        assert out["logits"].shape == (1, 10, TINY_CFG["vocab_size"])

    def test_M4_5_no_user_embedding(self, tiny_model):
        tokens = torch.randint(0, TINY_CFG["vocab_size"], (1, 10))
        out = tiny_model(tokens, user_embedding=None)
        assert out["logits"].shape == (1, 10, TINY_CFG["vocab_size"])

    def test_M4_6_with_spectral_features(self, tiny_model):
        B, T = 1, 15
        tokens = torch.randint(0, TINY_CFG["vocab_size"], (B, T))
        # T = 15 tokens = 3 events * 5 tokens/event
        spectral = torch.randn(B, 3, TINY_CFG["spectral_dim"])
        out = tiny_model(tokens, spectral_features=spectral, tokens_per_event=5)
        assert out["logits"].shape == (B, T, TINY_CFG["vocab_size"])

    def test_M4_7_logits_finite(self, tiny_model):
        tokens = torch.randint(0, TINY_CFG["vocab_size"], (1, 20))
        out = tiny_model(tokens)
        assert torch.isfinite(out["logits"]).all()

    def test_M4_8_causal_masking(self, tiny_model):
        """Extending the context beyond position t must not change logits at <=t."""
        torch.manual_seed(42)
        full = torch.randint(0, TINY_CFG["vocab_size"], (1, 20))
        prefix_len = 10
        prefix = full[:, :prefix_len]

        out_prefix = tiny_model(prefix)["logits"]
        out_full = tiny_model(full)["logits"][:, :prefix_len, :]

        # Allow small numerical tolerance (dropout disabled + eval mode).
        assert torch.allclose(out_prefix, out_full, atol=1e-5)


# --- ApolloModel._expand_spectral_to_tokens ------------------------------

class TestExpandSpectralToTokens:
    def test_M5_1_shape_and_M5_2_repeat(self, tiny_model):
        B, N, D = 1, 3, 32
        spectral = torch.arange(B * N * D, dtype=torch.float32).reshape(B, N, D)
        out = tiny_model._expand_spectral_to_tokens(
            spectral, tokens_per_event=5, total_tokens=15
        )
        assert out.shape == (B, 15, D)
        # Each event repeats 5 times
        for evt in range(N):
            for k in range(5):
                assert torch.equal(out[0, evt * 5 + k], spectral[0, evt])

    def test_M5_3_pad(self, tiny_model):
        B, N, D = 1, 2, 4
        spectral = torch.ones(B, N, D)
        out = tiny_model._expand_spectral_to_tokens(
            spectral, tokens_per_event=3, total_tokens=10
        )
        assert out.shape == (B, 10, D)
        # First 2*3=6 positions are ones; remainder is zero (pad).
        assert torch.all(out[0, :6] == 1)
        assert torch.all(out[0, 6:] == 0)

    def test_M5_4_truncate(self, tiny_model):
        B, N, D = 1, 4, 4
        spectral = torch.ones(B, N, D)
        out = tiny_model._expand_spectral_to_tokens(
            spectral, tokens_per_event=5, total_tokens=12
        )
        assert out.shape == (B, 12, D)


# --- ApolloModel.generate -------------------------------------------------

class TestGenerate:
    def test_M6_1_returns_tuple_and_length(self, tiny_model):
        prompt = torch.randint(0, TINY_CFG["vocab_size"] - 2, (1, 5))
        tokens, timbre = tiny_model.generate(
            prompt, max_new_tokens=10, temperature=1.0, top_k=10
        )
        assert tokens.shape[0] == 1
        assert tokens.shape[1] <= 5 + 10

    def test_M6_2_prompt_preserved(self, tiny_model):
        prompt = torch.randint(0, 100, (1, 5))
        tokens, _ = tiny_model.generate(
            prompt, max_new_tokens=8, temperature=1.0, top_k=10
        )
        assert torch.equal(tokens[:, :5], prompt)

    def test_M6_3_tokens_in_vocab(self, tiny_model):
        prompt = torch.randint(0, TINY_CFG["vocab_size"] - 2, (1, 3))
        tokens, _ = tiny_model.generate(
            prompt, max_new_tokens=10, temperature=1.0, top_k=10
        )
        assert tokens.min() >= 0
        assert tokens.max() < TINY_CFG["vocab_size"]

    def test_M6_5_timbre_length_matches_new_steps(self, tiny_model):
        prompt = torch.randint(0, TINY_CFG["vocab_size"] - 2, (1, 4))
        tokens, timbre = tiny_model.generate(
            prompt, max_new_tokens=6, temperature=1.0, top_k=5
        )
        n_new = tokens.shape[1] - 4
        assert timbre is not None
        assert timbre.shape == (1, n_new, TINY_CFG["n_timbre_outputs"])

    def test_M6_6_no_timbre_head_returns_none(self):
        m = ApolloModel(**{**TINY_CFG, "n_timbre_outputs": 0})
        m.eval()
        prompt = torch.randint(0, TINY_CFG["vocab_size"] - 2, (1, 3))
        _, timbre = m.generate(prompt, max_new_tokens=5, temperature=1.0, top_k=5)
        assert timbre is None

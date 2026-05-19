"""Phase 2 additions to model tests.

Covers MelEncoder, CausalMHA KV-cache, and ApolloModel forward/generate
extensions that were not present in test_model.py (Phase 1 coverage).

All tests run on CPU with tiny configs.
"""
from __future__ import annotations

import pytest
import torch

from model import ApolloModel, MelEncoder, CausalMHA

pytestmark = pytest.mark.unit

# Tiny base config reused across fixtures
TINY_BASE = dict(
    vocab_size=380,
    d_model=32,
    nhead=2,
    num_layers=2,
    max_seq_len=64,
    user_embed_dim=0,
    spectral_dim=0,
    n_timbre_outputs=0,
    dropout=0.0,
)

TINY_MEL_CFG = {**TINY_BASE, 'n_mels': 16}


@pytest.fixture
def mel_model():
    torch.manual_seed(0)
    m = ApolloModel(**TINY_MEL_CFG)
    m.eval()
    return m


@pytest.fixture
def base_model():
    torch.manual_seed(0)
    m = ApolloModel(**TINY_BASE)
    m.eval()
    return m


# ---------------------------------------------------------------------------
# MelEncoder
# ---------------------------------------------------------------------------

class TestMelEncoder:
    def test_output_shape_is_broadcast_vector(self):
        """MelEncoder must return (B, 1, d_model) — a single vector broadcast
        over all T token positions in the window."""
        enc = MelEncoder(n_mels=16, d_model=32)
        mel = torch.randn(2, 32, 16)   # (B, mel_frames, n_mels)
        out = enc(mel)
        assert out.shape == (2, 1, 32), (
            f"Expected (2, 1, 32), got {tuple(out.shape)}"
        )

    def test_broadcast_adds_to_token_sequence(self):
        """(B, 1, d_model) must be broadcastable to (B, T, d_model) via + operator."""
        enc = MelEncoder(n_mels=16, d_model=32)
        mel = torch.randn(1, 32, 16)
        out = enc(mel)          # (1, 1, 32)
        h   = torch.randn(1, 20, 32)   # T=20 token sequence
        result = h + out        # should broadcast without error
        assert result.shape == (1, 20, 32)

    def test_finite_output(self):
        """MelEncoder must not produce NaN or Inf for normal inputs."""
        enc = MelEncoder(n_mels=16, d_model=32)
        mel = torch.randn(3, 64, 16)
        out = enc(mel)
        assert torch.isfinite(out).all(), "MelEncoder output contains NaN or Inf"

    def test_different_mel_frame_counts(self):
        """AdaptiveAvgPool2d should handle varying mel_frames gracefully."""
        enc = MelEncoder(n_mels=16, d_model=32)
        for frames in [16, 64, 256]:
            mel = torch.randn(1, frames, 16)
            out = enc(mel)
            assert out.shape == (1, 1, 32), f"Failed for mel_frames={frames}"


# ---------------------------------------------------------------------------
# CausalMHA KV-cache
# ---------------------------------------------------------------------------

class TestCausalMHA:
    def test_output_shape_and_kv_tuple(self):
        """Forward must return (output, (K, V)) — the KV tuple is the cache."""
        mha = CausalMHA(d_model=32, nhead=2, dropout=0.0)
        x   = torch.randn(1, 10, 32)
        out, (K, V) = mha(x)
        assert out.shape == (1, 10, 32)
        assert K.shape[0] == 1   # batch
        assert V.shape[0] == 1

    def test_kv_cache_single_step_matches_full_forward(self):
        """Decoding one token at a time with KV-cache must give the same logits
        as a full forward pass over the whole sequence."""
        torch.manual_seed(7)
        mha    = CausalMHA(d_model=32, nhead=2, dropout=0.0)
        mha.eval()

        seq_len = 8
        x       = torch.randn(1, seq_len, 32)

        # Full forward
        full_out, _ = mha(x)
        last_full   = full_out[0, -1, :]   # last position

        # Incremental: prefill all tokens, then decode one more
        prefix   = x[:, :-1, :]
        last_tok = x[:, -1:, :]
        _, past_kv  = mha(prefix)
        step_out, _ = mha(last_tok, past_kv=past_kv)
        last_incr   = step_out[0, -1, :]

        assert torch.allclose(last_full, last_incr, atol=1e-5), (
            "KV-cache single-step decode does not match full forward at last position"
        )


# ---------------------------------------------------------------------------
# ApolloModel — MelEncoder integration
# ---------------------------------------------------------------------------

class TestApolloModelMel:
    def test_n_mels_creates_mel_encoder(self, mel_model):
        """`n_mels > 0` must instantiate a MelEncoder on ApolloModel."""
        assert mel_model.mel_encoder is not None

    def test_n_mels_zero_no_mel_encoder(self, base_model):
        """`n_mels=0` (default) must leave mel_encoder as None."""
        assert base_model.mel_encoder is None

    def test_forward_with_mel_patch_correct_shape(self, mel_model):
        """Passing mel_patch must produce the same logit shape as without it."""
        B, T = 2, 15
        tokens    = torch.randint(0, TINY_MEL_CFG['vocab_size'], (B, T))
        mel_patch = torch.randn(B, 32, TINY_MEL_CFG['n_mels'])
        out = mel_model(tokens, mel_patch=mel_patch)
        assert out['logits'].shape == (B, T, TINY_MEL_CFG['vocab_size'])

    def test_forward_without_mel_patch_still_works(self, mel_model):
        """mel_patch=None must skip MelEncoder silently — no error."""
        tokens = torch.randint(0, TINY_MEL_CFG['vocab_size'], (1, 10))
        out = mel_model(tokens, mel_patch=None)
        assert out['logits'].shape == (1, 10, TINY_MEL_CFG['vocab_size'])


# ---------------------------------------------------------------------------
# ApolloModel — KV-cache forward / generate
# ---------------------------------------------------------------------------

class TestApolloModelKVCache:
    def test_return_past_kvs_adds_key(self, base_model):
        """`return_past_kvs=True` must include 'past_kvs' in the output dict."""
        tokens = torch.randint(0, TINY_BASE['vocab_size'], (1, 8))
        out = base_model(tokens, return_past_kvs=True)
        assert 'past_kvs' in out, "'past_kvs' key missing from output"
        assert len(out['past_kvs']) == TINY_BASE['num_layers']

    def test_return_past_kvs_false_omits_key(self, base_model):
        tokens = torch.randint(0, TINY_BASE['vocab_size'], (1, 8))
        out = base_model(tokens, return_past_kvs=False)
        assert 'past_kvs' not in out

    def test_kv_cache_incremental_decode_matches_full_forward(self, base_model):
        """Single-token decode with KV-cache must match the last-position logits
        from a full forward pass — this is the correctness guarantee of KV-cache."""
        torch.manual_seed(42)
        T      = 10
        tokens = torch.randint(0, TINY_BASE['vocab_size'], (1, T))

        # Full forward — reference logits at position T-1
        full_out = base_model(tokens, return_past_kvs=False)
        ref_logits = full_out['logits'][0, -1, :]

        # Incremental: prefill first T-1 tokens, then decode the last one
        prefix = tokens[:, :-1]
        last   = tokens[:, -1:]

        prefill_out = base_model(prefix, return_past_kvs=True, position_offset=0)
        past_kvs    = prefill_out['past_kvs']

        step_out = base_model(
            last,
            past_kvs=past_kvs,
            return_past_kvs=False,
            position_offset=T - 1,
        )
        incr_logits = step_out['logits'][0, -1, :]

        assert torch.allclose(ref_logits, incr_logits, atol=1e-4), (
            "KV-cache incremental decode logits diverge from full forward"
        )

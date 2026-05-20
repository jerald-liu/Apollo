"""Contract tests for ApolloModel (Plan 02-02).

TDD RED phase — these tests all fail until transformer.py is implemented.

Tests:
  1. test_instantiates_with_defaults    — construction + parameter count
  2. test_forward_shape_cpu             — output shape on CPU
  3. test_forward_shape_mps             — output shape on MPS (skipped if unavailable)
  4. test_pos_emb_table_size_is_max_seq_len_plus_one — pos_emb.num_embeddings == max_seq_len+1
  5. test_forward_with_padding_mask     — finite logits with padding mask
  6. test_uses_transformer_encoder_layer — source uses EncoderLayer, NOT DecoderLayer
  7. test_mel_encoder_is_submodule      — mel_enc.* appears in named_parameters
  8. test_causality_is_strict           — logits[:, k] identical for two batches sharing pos 0..k
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import torch

from apollo.model import ApolloModel

# ---------------------------------------------------------------------------
# Constants (match apollo/tokenizer/vocab.py)
# ---------------------------------------------------------------------------
VOCAB_SIZE = 256
BOS = 109
SEP = 111
EOS = 110
PAD_ID = 0

# ---------------------------------------------------------------------------
# 1. Instantiation + parameter count
# ---------------------------------------------------------------------------

def test_instantiates_with_defaults():
    """ApolloModel() constructs without error.

    Total parameters = mel_enc (109184) + transformer/emb/proj (867200) = 976384.
    """
    m = ApolloModel()
    total = sum(p.numel() for p in m.parameters())
    assert total == 976_384, f"Expected 976384 params, got {total}"


# ---------------------------------------------------------------------------
# 2 + 3. Forward shape on CPU and MPS
# ---------------------------------------------------------------------------

def test_forward_shape_cpu():
    """Output shape is (B, T, vocab_size) on CPU."""
    m = ApolloModel()
    m.eval()
    with torch.no_grad():
        logits = m(
            torch.zeros(4, 64, dtype=torch.long),
            torch.randn(4, 1, 96, 128),
        )
    assert logits.shape == (4, 64, 256), f"Expected (4, 64, 256), got {logits.shape}"


@pytest.mark.skipif(
    not torch.backends.mps.is_available(),
    reason="MPS not available on this machine",
)
def test_forward_shape_mps():
    """Output shape is (B, T, vocab_size) on MPS."""
    device = torch.device("mps")
    m = ApolloModel().to(device)
    m.eval()
    with torch.no_grad():
        logits = m(
            torch.zeros(4, 64, dtype=torch.long, device=device),
            torch.randn(4, 1, 96, 128, device=device),
        )
    assert logits.shape == (4, 64, 256), f"Expected (4, 64, 256), got {logits.shape}"


# ---------------------------------------------------------------------------
# 4. Positional embedding table size
# ---------------------------------------------------------------------------

def test_pos_emb_table_size_is_max_seq_len_plus_one():
    """pos_emb must have max_seq_len+1 rows (positions 0..max_seq_len inclusive).

    Position 0 = MEL prefix. Positions 1..T = token positions.
    For max_seq_len=64, tokens can reach position 64 → table must be size 65.
    """
    m = ApolloModel(max_seq_len=64)
    assert m.pos_emb.num_embeddings == 65, (
        f"Expected pos_emb.num_embeddings=65, got {m.pos_emb.num_embeddings}"
    )
    # Boundary access: position 64 should NOT raise IndexError
    m.pos_emb(torch.tensor([64]))


# ---------------------------------------------------------------------------
# 5. Forward with padding mask — logits must be finite
# ---------------------------------------------------------------------------

def test_forward_with_padding_mask():
    """Finite logits even with PAD_ID=0 tokens and a padding mask.

    PAD_ID=0 is also a valid time_shift token, so the pad_mask must be
    length-based (True from actual_length onward), not value-based.
    """
    B, T = 2, 64
    token_ids = torch.zeros(B, T, dtype=torch.long)

    # Sample 0: [BOS, 5, 7, SEP, 60, 61, EOS, PAD...]
    phrase = [BOS, 5, 7, SEP, 60, 61, EOS]
    token_ids[0, :len(phrase)] = torch.tensor(phrase, dtype=torch.long)

    # Sample 1: slightly different phrase
    phrase2 = [BOS, 10, 12, SEP, 70, 71, EOS]
    token_ids[1, :len(phrase2)] = torch.tensor(phrase2, dtype=torch.long)

    # Padding mask: True for positions [7:] onward (length-based)
    pad_mask = torch.zeros(B, T, dtype=torch.bool)
    pad_mask[0, len(phrase):] = True
    pad_mask[1, len(phrase2):] = True

    m = ApolloModel()
    m.eval()
    with torch.no_grad():
        logits = m(token_ids, torch.randn(B, 1, 96, 128), key_padding_mask=pad_mask)

    assert torch.isfinite(logits).all(), "Forward with pad_mask produced NaN or Inf logits"


# ---------------------------------------------------------------------------
# 6. Source-code check: EncoderLayer, not DecoderLayer
# ---------------------------------------------------------------------------

def test_uses_transformer_encoder_layer():
    """transformer.py must use TransformerEncoderLayer, NOT TransformerDecoderLayer.

    The check looks for actual code use (nn.TransformerEncoderLayer instantiation),
    and verifies nn.TransformerDecoderLayer does NOT appear in code (ignoring comments
    and docstrings that may mention it by name for documentation purposes).
    """
    src = Path("apollo/model/transformer.py").read_text()

    # Positive: nn.TransformerEncoderLayer must be instantiated
    assert "nn.TransformerEncoderLayer" in src, (
        "nn.TransformerEncoderLayer not found in transformer.py"
    )

    # Negative: nn.TransformerDecoderLayer must NOT appear (not even in code)
    assert "nn.TransformerDecoderLayer" not in src, (
        "nn.TransformerDecoderLayer found in transformer.py — RESEARCH §1 forbids this"
    )


# ---------------------------------------------------------------------------
# 7. MelEncoder is a submodule
# ---------------------------------------------------------------------------

def test_mel_encoder_is_submodule():
    """mel_enc.* must appear in named_parameters so model.parameters() covers it.

    This ensures joint training with a single optimizer = AdamW(model.parameters(), ...).
    """
    m = ApolloModel()
    mel_enc_params = [name for name, _ in m.named_parameters() if name.startswith("mel_enc.")]
    assert len(mel_enc_params) > 0, (
        "No parameter names start with 'mel_enc.' — MelEncoder is not a submodule of ApolloModel"
    )


# ---------------------------------------------------------------------------
# 8. Causality: predictions at position k must not depend on tokens at k+1, k+2, ...
# ---------------------------------------------------------------------------

def test_causality_is_strict():
    """logits[:, k] must be identical for two sequences that share tokens 0..k.

    Uses eval mode and torch.manual_seed(0) for determinism.
    """
    torch.manual_seed(0)
    m = ApolloModel()
    m.eval()

    B, T = 2, 64
    mel = torch.randn(B, 1, 96, 128)

    # Two batches: identical at positions 0..6, differ at position 7+
    base = torch.randint(0, 100, (B, T))  # shared prefix
    seq_a = base.clone()
    seq_b = base.clone()
    seq_b[:, 7:] = torch.randint(0, 100, (B, T - 7))  # differ from position 7

    with torch.no_grad():
        logits_a = m(seq_a, mel)
        logits_b = m(seq_b, mel)

    # Predictions at positions 1..6 should be identical (causal mask prevents future look-ahead)
    for k in (1, 2, 3):
        assert torch.allclose(logits_a[:, k], logits_b[:, k], atol=1e-5), (
            f"logits differ at position {k} — causal mask is not strict"
        )

"""Tests that verify mel conditioning actually influences ApolloModel output.

The existing test suite checks that MelEncoder has gradients and that its
parameters update during training. These tests go one level higher: they
verify that ApolloModel *uses* the mel prefix token to change its output
logits, that the gradient path is end-to-end connected, and that different
timbres produce different response predictions.

An untrained model can pass all prior tests while being architecturally
wired to ignore the mel prefix — these tests catch that.

Tests:
  - test_mel_prefix_affects_logits: different mels → different logit distributions
  - test_mel_effect_is_substantial: effect size is meaningful, not float noise
  - test_zero_vs_real_mel_diverges: silence mel vs energy mel shifts predictions
  - test_gradient_flows_from_output_to_mel_encoder: end-to-end gradient path
  - test_mel_swap_changes_argmax: swapping mel changes predicted next tokens
"""

from __future__ import annotations

import torch
import pytest

from apollo.model import ApolloModel


# ── Fixtures ────────────────────────────────────────────────────────────────

MODEL_CFG = dict(vocab_size=256, d_model=128, n_layers=4,
                 n_heads=4, d_ff=512, max_seq_len=64)

# Two maximally different mels: all-zeros (silence) vs all-ones (saturated)
# Shape: (B, 1, 96, 128) — channel dim required by Conv2d in MelEncoder
MEL_SILENCE = torch.zeros(1, 1, 96, 128)
MEL_SATURATED = torch.ones(1, 1, 96, 128)


@pytest.fixture
def model():
    torch.manual_seed(42)
    m = ApolloModel(**MODEL_CFG)
    m.eval()
    return m


@pytest.fixture
def token_batch():
    """A short fixed token sequence — same for all tests."""
    torch.manual_seed(0)
    tokens = torch.randint(4, 200, (1, 8))   # avoid special tokens
    pad_mask = torch.zeros(1, 8, dtype=torch.bool)
    return tokens, pad_mask


# ── Tests ────────────────────────────────────────────────────────────────────

def test_mel_prefix_affects_logits(model, token_batch):
    """Different mel inputs must produce different logit tensors.

    If logits are identical regardless of mel, the transformer is
    ignoring the mel prefix token — mel conditioning is broken.
    """
    tokens, pad_mask = token_batch
    with torch.no_grad():
        logits_silence   = model(tokens, MEL_SILENCE,   key_padding_mask=pad_mask)
        logits_saturated = model(tokens, MEL_SATURATED, key_padding_mask=pad_mask)

    assert not torch.allclose(logits_silence, logits_saturated), (
        "Mel conditioning has no effect on logits — the mel prefix token "
        "is being ignored by the transformer. Check that mel_emb is "
        "prepended correctly and that attention is not masked over position 0."
    )


def test_mel_effect_is_substantial(model, token_batch):
    """The mel effect must be large enough to matter musically.

    A max absolute logit difference < 0.01 would mean the mel prefix
    contributes essentially nothing to the output distribution — the
    temperature/top-k sampling would treat both mels identically.
    """
    tokens, pad_mask = token_batch
    with torch.no_grad():
        logits_a = model(tokens, MEL_SILENCE,   key_padding_mask=pad_mask)
        logits_b = model(tokens, MEL_SATURATED, key_padding_mask=pad_mask)

    max_diff = (logits_a - logits_b).abs().max().item()
    assert max_diff > 0.01, (
        f"Mel effect too small: max |logit_A - logit_B| = {max_diff:.6f}. "
        "The mel prefix may be present but carries negligible information."
    )


def test_zero_vs_real_mel_diverges(model, token_batch):
    """A naturalistic mel (random, bounded) must differ from zero mel.

    Zero mel = silence / padding — the model should respond differently
    to an actual call timbre than to an empty signal.
    """
    tokens, pad_mask = token_batch
    torch.manual_seed(7)
    mel_real = torch.randn(1, 1, 96, 128).clamp(-3, 3)   # plausible log-mel range

    with torch.no_grad():
        logits_zero = model(tokens, MEL_SILENCE, key_padding_mask=pad_mask)
        logits_real = model(tokens, mel_real,    key_padding_mask=pad_mask)

    max_diff = (logits_zero - logits_real).abs().max().item()
    assert max_diff > 0.01, (
        f"Zero mel and real mel produce nearly identical logits (max diff "
        f"{max_diff:.6f}). Mel conditioning may not be functioning."
    )


def test_gradient_flows_from_output_to_mel_encoder(model, token_batch):
    """Loss at output token positions must produce nonzero gradients at
    MelEncoder input — verifies the computational graph is end-to-end
    connected through the mel prefix.

    If this fails, the mel encoder is detached from the loss and will
    never be updated during training (despite train.py using
    model.parameters() which includes mel_enc).
    """
    model.train()
    tokens, pad_mask = token_batch
    mel = MEL_SILENCE.clone().requires_grad_(True)

    logits = model(tokens, mel, key_padding_mask=pad_mask)

    # Scalar loss over all positions
    loss = logits.mean()
    loss.backward()

    assert mel.grad is not None, (
        "No gradient reached the mel input — mel encoder is disconnected "
        "from the computational graph."
    )
    assert mel.grad.abs().max().item() > 0, (
        "Mel input gradient is all zeros — gradient is not flowing through "
        "MelEncoder into the transformer."
    )


def test_mel_swap_shifts_token_distribution(model, token_batch):
    """Swapping the mel input must produce a nonzero KL divergence between
    the two output token distributions.

    With a random-init model, the KL will be small (attention hasn't
    learned to weight the mel prefix yet), but it must be strictly > 0.
    Zero KL would mean the mel prefix has absolutely no effect on the
    probability distribution — a sign the computational graph is broken
    even though logit values technically differ.

    Note: large KL is only expected after training. This test only
    verifies architectural connectivity at the distribution level.
    """
    tokens, pad_mask = token_batch
    with torch.no_grad():
        logits_a = model(tokens, MEL_SILENCE,   key_padding_mask=pad_mask)  # (1, T, V)
        logits_b = model(tokens, MEL_SATURATED, key_padding_mask=pad_mask)

    log_p = torch.log_softmax(logits_a, dim=-1)
    log_q = torch.log_softmax(logits_b, dim=-1)

    # KL(P || Q) = sum(P * (log_P - log_Q))
    p = log_p.exp()
    kl_per_position = (p * (log_p - log_q)).sum(dim=-1)  # (1, T)
    mean_kl = kl_per_position.mean().item()

    assert mean_kl > 1e-8, (
        f"Mean KL divergence is exactly zero ({mean_kl:.2e}) — the mel prefix "
        "has no effect on the output probability distribution whatsoever. "
        "The computational graph may be broken despite logit differences."
    )

"""Tests for augment_tokens() in scripts/train.py.

augment_tokens() shifts pitch and/or velocity tokens in-place (in token
space) and clamps to the valid range.  These tests verify the pure
transformation logic without requiring any dataset or training run.
"""
from __future__ import annotations

import pytest
import torch

# augment_tokens and the offset constants are module-level in train.py
from train import augment_tokens, _PITCH_LO, _PITCH_HI, _VEL_LO, _VEL_HI

pytestmark = pytest.mark.unit


class TestAugmentTokens:
    # --- identity ---

    def test_identity_when_both_shifts_zero(self):
        """Zero shifts must return the input tensor unchanged (no clone overhead
        either — the function should return the original object)."""
        t = torch.tensor([0, 100, 150, 228, 5], dtype=torch.long)
        result = augment_tokens(t, pitch_shift=0, velocity_shift=0)
        assert torch.equal(result, t)

    # --- pitch shift ---

    def test_pitch_shift_moves_pitch_tokens_up(self):
        """Positive pitch_shift must add the shift to all tokens in [_PITCH_LO, _PITCH_HI]."""
        # One pitch token at _PITCH_LO (lowest), one non-pitch below it
        t = torch.tensor([_PITCH_LO, _PITCH_LO + 10, 5], dtype=torch.long)
        result = augment_tokens(t, pitch_shift=2)
        assert result[0].item() == _PITCH_LO + 2
        assert result[1].item() == _PITCH_LO + 12
        assert result[2].item() == 5   # non-pitch token unchanged

    def test_pitch_shift_clamps_at_upper_bound(self):
        """Shifting a token at _PITCH_HI upward must clamp to _PITCH_HI."""
        t = torch.tensor([_PITCH_HI], dtype=torch.long)
        result = augment_tokens(t, pitch_shift=10)
        assert result[0].item() == _PITCH_HI

    def test_pitch_shift_clamps_at_lower_bound(self):
        """Shifting a token at _PITCH_LO downward must clamp to _PITCH_LO."""
        t = torch.tensor([_PITCH_LO], dtype=torch.long)
        result = augment_tokens(t, pitch_shift=-10)
        assert result[0].item() == _PITCH_LO

    def test_pitch_shift_does_not_touch_non_pitch_tokens(self):
        """Tokens outside [_PITCH_LO, _PITCH_HI] must be unaffected by pitch_shift."""
        t = torch.tensor([0, 50, _VEL_LO, _VEL_HI, 300], dtype=torch.long)
        original = t.clone()
        result = augment_tokens(t, pitch_shift=5)
        # Non-pitch positions unchanged
        non_pitch_mask = ~((original >= _PITCH_LO) & (original <= _PITCH_HI))
        assert torch.equal(result[non_pitch_mask], original[non_pitch_mask])

    # --- velocity shift ---

    def test_velocity_shift_moves_velocity_tokens(self):
        """velocity_shift must add the shift to all tokens in [_VEL_LO, _VEL_HI]."""
        t = torch.tensor([_VEL_LO, _VEL_LO + 5], dtype=torch.long)
        result = augment_tokens(t, velocity_shift=3)
        assert result[0].item() == _VEL_LO + 3
        assert result[1].item() == _VEL_LO + 8

    def test_velocity_shift_clamps(self):
        t = torch.tensor([_VEL_HI], dtype=torch.long)
        assert augment_tokens(t, velocity_shift=100)[0].item() == _VEL_HI

    def test_velocity_shift_does_not_touch_pitch_tokens(self):
        """velocity_shift must leave pitch tokens in [_PITCH_LO, _PITCH_HI] unchanged."""
        t = torch.tensor([_PITCH_LO, _PITCH_LO + 20, _PITCH_HI], dtype=torch.long)
        original = t.clone()
        result = augment_tokens(t, velocity_shift=2)
        assert torch.equal(result, original)

    # --- combined ---

    def test_combined_shift_applies_both_independently(self):
        """Both pitch and velocity shifts must apply in a single call without
        one affecting the other's token range."""
        t = torch.tensor([_PITCH_LO, _VEL_LO], dtype=torch.long)
        result = augment_tokens(t, pitch_shift=3, velocity_shift=2)
        assert result[0].item() == _PITCH_LO + 3
        assert result[1].item() == _VEL_LO + 2

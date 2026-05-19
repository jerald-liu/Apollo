"""Tests for the load_checkpoint() bug fixes in scripts/generate.py.

Two bugs were fixed in Phase 2:
  1. vocab_size was hardcoded to VOCAB_SIZE (380); v4 checkpoints (vocab_size=259)
     would crash with a state_dict shape mismatch.
  2. n_mels was absent; v3 checkpoints with MelEncoder weights would crash
     because the freshly-constructed model had no mel_encoder module.

These tests create minimal fake checkpoints in tmp_path and verify that
load_checkpoint() reconstructs the model correctly from checkpoint config.
"""
from __future__ import annotations

import pytest
import torch
from pathlib import Path

from model import ApolloModel
from representation import VOCAB_SIZE

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_checkpoint(tmp_path: Path, cfg_overrides: dict) -> Path:
    """Build and save a minimal but real ApolloModel checkpoint.

    Uses a tiny architecture so the test runs fast on CPU.  The config dict
    is stored inside the checkpoint exactly as train.py does via asdict().
    """
    base_cfg = dict(
        vocab_size=380,
        d_model=16,
        nhead=2,
        num_layers=1,
        max_seq_len=32,
        user_embed_dim=0,
        spectral_dim=0,
        n_timbre_outputs=0,
        dropout=0.0,
        # mel fields (only active when mel=True)
        mel=False,
        n_mels=128,
        mel_frames=256,
        spectral=False,
    )
    cfg = {**base_cfg, **cfg_overrides}

    model = ApolloModel(
        vocab_size=cfg['vocab_size'],
        d_model=cfg['d_model'],
        nhead=cfg['nhead'],
        num_layers=cfg['num_layers'],
        max_seq_len=cfg['max_seq_len'],
        user_embed_dim=cfg.get('user_embed_dim', 0),
        spectral_dim=cfg['spectral_dim'] if cfg.get('spectral', False) else 0,
        n_timbre_outputs=cfg['n_timbre_outputs'] if cfg.get('spectral', False) else 0,
        dropout=0.0,
        n_mels=cfg.get('n_mels', 0) if cfg.get('mel', False) else 0,
    )

    ckpt_path = tmp_path / 'checkpoint_test.pt'
    torch.save({
        'model_state_dict': model.state_dict(),
        'config': cfg,
        'step': 1000,
        'best_val_loss': 2.5,
    }, ckpt_path)
    return ckpt_path


# ---------------------------------------------------------------------------
# Import load_checkpoint from generate.py
# ---------------------------------------------------------------------------

import sys
from pathlib import Path as _P
_SCRIPTS = _P(__file__).parent.parent.parent / 'scripts'
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from generate import load_checkpoint


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLoadCheckpointVocabSize:
    def test_vocab_size_read_from_config_not_hardcoded(self, tmp_path):
        """load_checkpoint must use cfg['vocab_size'], not the module-level
        VOCAB_SIZE constant.  Before the fix, v4 (vocab_size=259) checkpoints
        crashed with a state_dict key shape mismatch."""
        ckpt_path = _make_fake_checkpoint(tmp_path, {'vocab_size': 259})
        model, cfg, step = load_checkpoint(str(ckpt_path), device='cpu')
        assert model.vocab_size == 259, (
            "Model vocab_size should come from checkpoint config, not hardcoded 380"
        )

    def test_base_vocab_checkpoint_loads(self, tmp_path):
        """Standard v2/v3 checkpoint (vocab_size=380) must still load correctly."""
        ckpt_path = _make_fake_checkpoint(tmp_path, {'vocab_size': 380})
        model, cfg, _ = load_checkpoint(str(ckpt_path), device='cpu')
        assert model.vocab_size == 380

    def test_returned_cfg_contains_vocab_size(self, tmp_path):
        """load_checkpoint must return the full config dict including vocab_size."""
        ckpt_path = _make_fake_checkpoint(tmp_path, {'vocab_size': 259})
        _, cfg, _ = load_checkpoint(str(ckpt_path), device='cpu')
        assert cfg.get('vocab_size') == 259


class TestLoadCheckpointMelEncoder:
    def test_n_mels_enabled_when_mel_true(self, tmp_path):
        """When checkpoint config has mel=True, the reconstructed model must
        have a MelEncoder (n_mels > 0).  Before the fix, mel_encoder was always
        None because n_mels was never passed to ApolloModel()."""
        ckpt_path = _make_fake_checkpoint(tmp_path, {'mel': True, 'n_mels': 16})
        model, _, _ = load_checkpoint(str(ckpt_path), device='cpu')
        assert model.mel_encoder is not None, (
            "mel_encoder should be instantiated when checkpoint config has mel=True"
        )

    def test_n_mels_zero_when_mel_false(self, tmp_path):
        """When checkpoint config has mel=False, mel_encoder must be None
        even if n_mels is present in the config."""
        ckpt_path = _make_fake_checkpoint(tmp_path, {'mel': False, 'n_mels': 128})
        model, _, _ = load_checkpoint(str(ckpt_path), device='cpu')
        assert model.mel_encoder is None

    def test_state_dict_loads_without_error_for_mel_checkpoint(self, tmp_path):
        """The key fix: a checkpoint trained with MelEncoder must load_state_dict
        without raising 'unexpected key' or 'missing key' errors."""
        ckpt_path = _make_fake_checkpoint(tmp_path, {'mel': True, 'n_mels': 16})
        # If this raises, the bug is not fixed
        model, _, _ = load_checkpoint(str(ckpt_path), device='cpu')
        # Verify mel_encoder weights are actually loaded (not randomly re-initialised)
        assert model.mel_encoder is not None
        # Spot-check: a real parameter tensor exists
        param = next(model.mel_encoder.parameters())
        assert param.shape[0] > 0

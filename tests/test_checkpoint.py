"""Checkpoint save/load round-trip tests (TRAIN-06, D-23, D-24).

Tests:
  - Exact 5-key contract in saved checkpoint dict
  - Round-trip reconstruction produces bit-identical forward output
  - mel_encoder_state_dict separately loadable into a fresh MelEncoder
  - model_config has expected keys
  - training_meta has expected keys
  - vocab matches Phase 1 Vocab constants
  - weights_only=False present in load_checkpoint (D-24)
  - File exists and is non-trivially sized
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

import pytest
import torch

from apollo.model import ApolloModel, MelEncoder
from apollo.model.train import load_checkpoint, save_checkpoint


MODEL_CONFIG = {
    "vocab_size": 256,
    "d_model": 128,
    "n_layers": 4,
    "n_heads": 4,
    "d_ff": 512,
    "max_seq_len": 64,
}

TRAINING_META = {
    "n_epochs": 1,
    "n_pairs": 5,
    "final_loss": 3.5,
    "type_accuracy": 0.42,
    "timestamp": "2026-01-01T00:00:00Z",
}

VOCAB_STUB = {
    "BOS": 109,
    "EOS": 110,
    "SEP": 111,
    "VOCAB_SIZE": 256,
    "ACTIVE_VOCAB": 112,
    "N_PITCH": 37,
    "N_TIME": 32,
    "N_VELOCITY": 16,
    "N_DURATION": 24,
}


@pytest.fixture
def saved_ckpt(tmp_path):
    """Create a model, save checkpoint, return (ckpt_path, model_a)."""
    torch.manual_seed(42)
    model = ApolloModel(**MODEL_CONFIG)
    ckpt_path = tmp_path / "test.pt"
    save_checkpoint(
        model=model,
        vocab_dict=VOCAB_STUB,
        model_config=MODEL_CONFIG,
        training_meta=TRAINING_META,
        out_path=str(ckpt_path),
    )
    return ckpt_path, model


def test_checkpoint_keys(saved_ckpt):
    """Saved checkpoint has EXACTLY the five required top-level keys (D-23)."""
    ckpt_path, _ = saved_ckpt
    ckpt = load_checkpoint(str(ckpt_path))
    expected_keys = {
        "model_state_dict",
        "mel_encoder_state_dict",
        "vocab",
        "model_config",
        "training_meta",
    }
    assert set(ckpt.keys()) == expected_keys


def test_checkpoint_round_trip_reconstructs_model(saved_ckpt):
    """Load state_dict into a new model; forward outputs must be bit-identical."""
    ckpt_path, model_a = saved_ckpt
    ckpt = load_checkpoint(str(ckpt_path))

    # Build a fresh model with DIFFERENT seed
    torch.manual_seed(99)
    model_b = ApolloModel(**MODEL_CONFIG)
    model_b.load_state_dict(ckpt["model_state_dict"])

    # Same dummy input
    torch.manual_seed(0)
    token_ids = torch.randint(0, 112, (1, 64))
    mel = torch.randn(1, 1, 96, 128)

    model_a.eval()
    model_b.eval()
    with torch.no_grad():
        out_a = model_a(token_ids, mel)
        out_b = model_b(token_ids, mel)

    assert torch.allclose(out_a, out_b, atol=1e-6), (
        "Forward outputs differ after round-trip: max diff = "
        f"{(out_a - out_b).abs().max().item()}"
    )


def test_checkpoint_mel_encoder_state_separately_loadable(saved_ckpt):
    """mel_encoder_state_dict can be loaded into a standalone MelEncoder (D-23)."""
    ckpt_path, _ = saved_ckpt
    ckpt = load_checkpoint(str(ckpt_path))

    fresh_enc = MelEncoder(d_model=MODEL_CONFIG["d_model"])
    missing, unexpected = fresh_enc.load_state_dict(
        ckpt["mel_encoder_state_dict"], strict=True
    )
    assert not missing, f"Missing keys: {missing}"
    assert not unexpected, f"Unexpected keys: {unexpected}"


def test_checkpoint_model_config_has_expected_keys(saved_ckpt):
    """ckpt['model_config'] has exactly the expected keys."""
    ckpt_path, _ = saved_ckpt
    ckpt = load_checkpoint(str(ckpt_path))
    expected = {"d_model", "n_layers", "n_heads", "d_ff", "max_seq_len", "vocab_size"}
    assert set(ckpt["model_config"].keys()) == expected


def test_checkpoint_training_meta_has_expected_keys(saved_ckpt):
    """ckpt['training_meta'] has exactly the expected keys."""
    ckpt_path, _ = saved_ckpt
    ckpt = load_checkpoint(str(ckpt_path))
    expected = {"n_epochs", "n_pairs", "final_loss", "type_accuracy", "timestamp"}
    assert set(ckpt["training_meta"].keys()) == expected


def test_checkpoint_vocab_matches_phase1_artifact(saved_ckpt):
    """ckpt['vocab'] contains required Phase 1 Vocab subkeys."""
    ckpt_path, _ = saved_ckpt
    ckpt = load_checkpoint(str(ckpt_path))
    required_keys = {
        "BOS", "EOS", "SEP", "VOCAB_SIZE", "ACTIVE_VOCAB",
        "N_PITCH", "N_TIME", "N_VELOCITY", "N_DURATION",
    }
    assert required_keys.issubset(set(ckpt["vocab"].keys()))
    # Spot-check canonical values from Phase 1
    assert ckpt["vocab"]["BOS"] == 109
    assert ckpt["vocab"]["EOS"] == 110
    assert ckpt["vocab"]["SEP"] == 111
    assert ckpt["vocab"]["VOCAB_SIZE"] == 256


def test_load_checkpoint_uses_weights_only_false():
    """load_checkpoint source code must contain weights_only=False (D-24)."""
    import inspect
    import apollo.model.train as train_mod

    src = inspect.getsource(train_mod.load_checkpoint)
    assert "weights_only=False" in src, (
        "load_checkpoint must use weights_only=False (D-24, trusted-local checkpoint)"
    )


def test_checkpoint_file_exists_under_models_pattern(tmp_path):
    """Saved checkpoint file exists and is non-empty (> 1 MB)."""
    torch.manual_seed(0)
    model = ApolloModel(**MODEL_CONFIG)
    ckpt_path = tmp_path / "smoke-20260101T000000Z.pt"
    save_checkpoint(
        model=model,
        vocab_dict=VOCAB_STUB,
        model_config=MODEL_CONFIG,
        training_meta=TRAINING_META,
        out_path=str(ckpt_path),
    )
    assert ckpt_path.exists(), "Checkpoint file does not exist"
    size_mb = ckpt_path.stat().st_size / (1024 * 1024)
    assert size_mb > 1.0, (
        f"Checkpoint too small: {size_mb:.2f} MB (expected > 1 MB; RESEARCH §9 est. ~3.8 MB)"
    )

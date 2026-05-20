"""Tests for apollo/scripts/generate.py (INFER-01..INFER-04)."""
from __future__ import annotations

from pathlib import Path

import pretty_midi
import pytest
import torch

import apollo.scripts.generate as generate
from apollo.ingest.artifact import ingest
from apollo.ingest.mock import synthesize_pair
from apollo.model import ApolloModel
from apollo.model.train import save_checkpoint


MODEL_CONFIG = {
    "vocab_size": 256,
    "d_model": 128,
    "n_layers": 4,
    "n_heads": 4,
    "d_ff": 512,
    "max_seq_len": 64,
}


@pytest.fixture(scope="module")
def mock_ckpt(tmp_path_factory):
    """Synthesize one pair, build artifact, save an untrained checkpoint."""
    root = tmp_path_factory.mktemp("gen_pairs")
    synthesize_pair(root, nnn="000")
    artifact = ingest(str(root))

    torch.manual_seed(0)
    model = ApolloModel(**MODEL_CONFIG)
    ckpt_path = root / "test_ckpt.pt"
    save_checkpoint(
        model=model,
        vocab_dict=artifact["vocab"],
        model_config=MODEL_CONFIG,
        training_meta={
            "n_epochs": 0,
            "n_pairs": 1,
            "final_loss": 0.0,
            "type_accuracy": 0.0,
            "timestamp": "test",
        },
        out_path=str(ckpt_path),
    )
    return ckpt_path, root / "000"


def test_generate_smoke_creates_response_midi(mock_ckpt):
    ckpt_path, pair_dir = mock_ckpt
    # Clear any stale responses from prior runs
    for p in pair_dir.glob("response_*.mid"):
        p.unlink()
    rc = generate.main([
        str(ckpt_path),
        str(pair_dir / "call.mid"),
        str(pair_dir / "call.wav"),
    ])
    assert rc == 0, f"generate.main returned {rc}"
    assert (pair_dir / "response_001.mid").exists()


def test_generate_output_is_valid_midi(mock_ckpt):
    _, pair_dir = mock_ckpt
    # Verify the file parses without exception. An untrained model may emit zero
    # valid 4-groups (empty notes), so pretty_midi returns no instruments — that's
    # fine; the contract is a parseable MIDI file, not a non-empty one.
    pm = pretty_midi.PrettyMIDI(str(pair_dir / "response_001.mid"))
    assert pm is not None


def test_generate_n_samples_naming(mock_ckpt):
    """D-17: --n N creates N new response files at the next available indices."""
    ckpt_path, pair_dir = mock_ckpt
    # Ensure 001 exists (from prior test)
    assert (pair_dir / "response_001.mid").exists()
    rc = generate.main([
        str(ckpt_path),
        str(pair_dir / "call.mid"),
        str(pair_dir / "call.wav"),
        "--n", "3",
        "--max-tokens", "8",
    ])
    assert rc == 0
    for i in [2, 3, 4]:
        assert (pair_dir / f"response_{i:03d}.mid").exists(), \
            f"expected response_{i:03d}.mid"


def test_generate_temperature_topk_flags(mock_ckpt):
    """INFER-03: --temperature, --top-k, --max-tokens are accepted and run cleanly."""
    ckpt_path, pair_dir = mock_ckpt
    rc = generate.main([
        str(ckpt_path),
        str(pair_dir / "call.mid"),
        str(pair_dir / "call.wav"),
        "--temperature", "0.5",
        "--top-k", "5",
        "--max-tokens", "8",
    ])
    assert rc == 0


def test_generate_missing_call_mid_returns_error(mock_ckpt, tmp_path):
    """Missing call.mid path produces non-zero exit code (no traceback to user)."""
    ckpt_path, pair_dir = mock_ckpt
    rc = generate.main([
        str(ckpt_path),
        str(tmp_path / "does_not_exist.mid"),
        str(pair_dir / "call.wav"),
    ])
    assert rc != 0

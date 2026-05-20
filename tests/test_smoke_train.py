"""Smoke-train integration tests — TRAIN-04 hard gate.

Tests:
  - test_smoke_train_hits_accuracy_gate: type_accuracy > 0.95 (TRAIN-04 hard gate)
  - test_smoke_train_wall_clock_under_120s: elapsed < 120 s on MPS/CPU (TRAIN-05)
  - test_smoke_train_creates_models_dir_artifact: checkpoint exists at returned path
  - test_smoke_train_runs_from_random_init: no .pt files beforehand, exactly one after (TRAIN-03)

IMPORTANT: These tests call `train_smoke.main()` which runs 50 training epochs on
10 mock pairs. They are integration tests — expect ~20-60 seconds on MPS.
"""

from __future__ import annotations

import glob
import time
from pathlib import Path

import pytest
import torch

# These imports will fail until Task 2 is implemented — that's the RED state.
import apollo.scripts.train_smoke as train_smoke
from apollo.ingest.artifact import ingest
from apollo.ingest.mock import synthesize_pair
from apollo.model import ApolloDataset, ApolloModel, collate_fn, get_device
from apollo.model.train import load_checkpoint
from torch.utils.data import DataLoader


N_PAIRS = 10
N_EPOCHS = 50


def test_smoke_train_hits_accuracy_gate(tmp_path):
    """TRAIN-04 hard gate: smoke train reaches > 0.95 type-accuracy on mock pairs.

    Procedure:
      1. Run main() to train and save a checkpoint.
      2. Load checkpoint and reconstruct model.
      3. Rebuild the same artifact with the same seed and evaluate.
      4. Assert type_accuracy > 0.95 (hard gate — failure is a Phase 2 failure).
      5. Also assert that training_meta['type_accuracy'] > 0.95 (script self-reports correctly).
    """
    ckpt_path = train_smoke.main(
        n_pairs=N_PAIRS,
        n_epochs=N_EPOCHS,
        batch_size=4,
        lr=1e-3,
        seed=0,
        out_dir=str(tmp_path),
    )

    ckpt = load_checkpoint(ckpt_path)

    # Reconstruct model
    device = get_device()
    model = ApolloModel(**ckpt["model_config"])
    model.load_state_dict(ckpt["model_state_dict"])
    model.to(device)
    model.eval()

    # Rebuild artifact with same seed
    torch.manual_seed(0)
    data_dir = tmp_path / "eval_pairs"
    for i in range(N_PAIRS):
        synthesize_pair(data_dir, nnn=f"{i:03d}")
    artifact = ingest(str(data_dir))

    ds = ApolloDataset(artifact, split="all")
    dl = DataLoader(ds, batch_size=N_PAIRS, shuffle=False, collate_fn=collate_fn)

    # Aggregate logits and token_ids
    all_logits = []
    all_token_ids = []
    with torch.no_grad():
        for token_ids, pad_mask, mel in dl:
            token_ids = token_ids.to(device)
            pad_mask = pad_mask.to(device)
            mel = mel.to(device).float()
            logits = model(token_ids, mel, key_padding_mask=pad_mask)
            all_logits.append(logits.cpu())
            all_token_ids.append(token_ids.cpu())

    from apollo.model import compute_type_accuracy
    logits_cat = torch.cat(all_logits, dim=0)
    ids_cat = torch.cat(all_token_ids, dim=0)
    type_accuracy = compute_type_accuracy(logits_cat, ids_cat)

    print(f"\n[TRAIN-04] type_accuracy = {type_accuracy:.4f}")  # visible in pytest -s

    # Hard gate — failure here is a Phase 2 failure
    assert type_accuracy > 0.95, (
        f"TRAIN-04 FAILED: type_accuracy={type_accuracy:.4f} <= 0.95. "
        "Architecture or mask is broken — do not paper over with more epochs."
    )

    # Also verify the value the script saved in training_meta
    assert ckpt["training_meta"]["type_accuracy"] > 0.95, (
        "training_meta['type_accuracy'] does not meet gate "
        f"(got {ckpt['training_meta']['type_accuracy']:.4f})"
    )


def test_smoke_train_wall_clock_under_120s(tmp_path):
    """TRAIN-05: smoke train completes in under 120 seconds on local device."""
    start = time.perf_counter()
    train_smoke.main(
        n_pairs=N_PAIRS,
        n_epochs=N_EPOCHS,
        batch_size=4,
        lr=1e-3,
        seed=1,
        out_dir=str(tmp_path),
    )
    elapsed = time.perf_counter() - start
    print(f"\n[TRAIN-05] wall_clock = {elapsed:.2f}s")
    assert elapsed < 120.0, (
        f"TRAIN-05 FAILED: smoke train took {elapsed:.2f}s > 120s wall-clock budget"
    )


def test_smoke_train_creates_models_dir_artifact(tmp_path):
    """Checkpoint file exists at the returned path and matches smoke-*.pt pattern."""
    ckpt_path = train_smoke.main(
        n_pairs=N_PAIRS,
        n_epochs=N_EPOCHS,
        batch_size=4,
        lr=1e-3,
        seed=2,
        out_dir=str(tmp_path),
    )
    p = Path(ckpt_path)
    assert p.exists(), f"Checkpoint file not found at {ckpt_path}"
    assert p.name.startswith("smoke-") and p.name.endswith(".pt"), (
        f"Expected smoke-*.pt, got {p.name}"
    )


def test_smoke_train_runs_from_random_init(tmp_path):
    """No .pt files before main(); exactly one .pt file after (TRAIN-03 — no warm-start)."""
    before = list(tmp_path.glob("*.pt"))
    assert len(before) == 0, f"Unexpected .pt files before training: {before}"

    train_smoke.main(
        n_pairs=N_PAIRS,
        n_epochs=N_EPOCHS,
        batch_size=4,
        lr=1e-3,
        seed=3,
        out_dir=str(tmp_path),
    )

    after = list(tmp_path.glob("*.pt"))
    assert len(after) == 1, (
        f"Expected exactly 1 .pt file after smoke train, found {len(after)}: {after}"
    )

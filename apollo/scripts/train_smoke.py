"""Smoke train CLI: 10 mock pairs -> train -> save checkpoint.

Usage: python -m apollo.scripts.train_smoke

Procedure:
  1. Set torch.manual_seed(seed)
  2. Build tmp_dir with n_pairs mock pairs via synthesize_pair
  3. Run ingest() to produce the artifact
  4. Build ApolloDataset(artifact, split="all") + DataLoader(batch_size, collate_fn)
  5. Build ApolloModel() with defaults (D-07)
  6. Move to get_device(), run run_training(model, dataloader, n_epochs=..., lr=...)
  7. Eval model on the full training set, compute type_accuracy
  8. Save checkpoint to <out_dir>/smoke-<UTC timestamp>.pt
  9. Print final loss + type_accuracy + checkpoint path

TRAIN-03: this script does NOT load any prior checkpoint — random init only.
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import torch
from torch.utils.data import DataLoader

from apollo.ingest.artifact import ingest
from apollo.ingest.mock import synthesize_pair
from apollo.model import (
    ApolloDataset,
    ApolloModel,
    collate_fn,
    get_device,
    run_training,
)
from apollo.model.metrics import token_category
from apollo.model.train import save_checkpoint


DEFAULT_MODEL_CONFIG = {
    "vocab_size": 256,
    "d_model": 128,
    "n_layers": 4,
    "n_heads": 4,
    "d_ff": 512,
    "max_seq_len": 64,
}

# SEP token ID (matches packer.SEP = Vocab().SEP = 111)
_SEP_ID = 111


def _build_artifact(n_pairs: int, tmp_root: Path) -> dict:
    """Synthesize n_pairs mock pairs and ingest them into an artifact."""
    for i in range(n_pairs):
        synthesize_pair(tmp_root, nnn=f"{i:03d}")
    return ingest(str(tmp_root))


@torch.no_grad()
def _evaluate_type_accuracy(
    model: ApolloModel,
    dataloader: DataLoader,
    device: torch.device,
) -> float:
    """Aggregate type-accuracy across all batches in the dataloader.

    Uses the same j >= sep_pos boundary as compute_masked_loss / compute_type_accuracy
    (RESEARCH pitfall #2). Aggregates numerators and denominators across batches
    before computing the final ratio — avoids averaging-of-averages bias.
    """
    model.eval()
    total_correct = 0.0
    total_count = 0.0

    for token_ids, pad_mask, mel in dataloader:
        token_ids = token_ids.to(device)
        pad_mask = pad_mask.to(device)
        mel = mel.to(device).float()
        logits = model(token_ids, mel, key_padding_mask=pad_mask)

        B, T, V = logits.shape
        preds = logits[:, :-1].argmax(dim=-1)      # (B, T-1)
        targets = token_ids[:, 1:]                  # (B, T-1)

        sep_pos = (token_ids == _SEP_ID).long().argmax(dim=1)   # (B,)
        j_range = torch.arange(T - 1, device=device).unsqueeze(0)
        resp_mask = j_range >= sep_pos.unsqueeze(1)              # (B, T-1)

        correct = (token_category(preds) == token_category(targets)) & resp_mask
        total_correct += correct.float().sum().item()
        total_count += resp_mask.float().sum().item()

    return total_correct / max(total_count, 1e-8)


def main(
    n_pairs: int = 10,
    n_epochs: int = 50,
    batch_size: int = 4,
    lr: float = 1e-3,
    seed: int = 0,
    out_dir: str | Path = "models",
) -> str:
    """End-to-end smoke train. Returns checkpoint path.

    TRAIN-03: does NOT load any prior checkpoint — random init only.
    """
    torch.manual_seed(seed)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp) / "pairs"
        artifact = _build_artifact(n_pairs, tmp_root)

        ds = ApolloDataset(artifact, split="all")
        dl = DataLoader(ds, batch_size=batch_size, shuffle=True, collate_fn=collate_fn)

        device = get_device()
        model = ApolloModel(**DEFAULT_MODEL_CONFIG).to(device)

        result = run_training(model, dl, n_epochs=n_epochs, lr=lr, device=device)
        final_loss = result["final_loss"]

        # Eval pass on the same training set (overfit-by-design per D-22)
        eval_dl = DataLoader(
            ds, batch_size=batch_size, shuffle=False, collate_fn=collate_fn
        )
        type_acc = _evaluate_type_accuracy(model, eval_dl, device)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = Path(out_dir) / f"smoke-{timestamp}.pt"

        training_meta = {
            "n_epochs":      n_epochs,
            "n_pairs":       n_pairs,
            "final_loss":    float(final_loss),
            "type_accuracy": float(type_acc),
            "timestamp":     datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

        save_checkpoint(
            model=model,
            vocab_dict=artifact["vocab"],
            model_config=DEFAULT_MODEL_CONFIG,
            training_meta=training_meta,
            out_path=str(out_path),
        )

        print(
            f"smoke train done: n_pairs={n_pairs} n_epochs={n_epochs} "
            f"final_loss={final_loss:.4f} type_accuracy={type_acc:.4f} "
            f"checkpoint={out_path}"
        )
        return str(out_path)


if __name__ == "__main__":
    main()

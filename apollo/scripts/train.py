"""apollo/scripts/train.py — production training CLI for the Apollo v1 model.

Trains on a real data/pairs/ corpus with:
- OneCycleLR schedule (D-09): 5% warmup + cosine annealing
- Held-out loss logging every --log-every epochs (D-12)
- Checkpoint naming: models/run-{iteration:02d}-{timestamp}.pt (D-10)
- Optional CSV logging at logs/run-{iteration:02d}-{timestamp}.csv (D-12)

Distinct from train_smoke.py, which uses mock data and is CI-only.
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

import torch
from torch.utils.data import DataLoader

from apollo.ingest import IngestError, ingest
from apollo.model import (
    ApolloDataset,
    ApolloModel,
    collate_fn,
    get_device,
    train_epoch,
)
from apollo.model.train import compute_masked_loss, save_checkpoint


DEFAULT_MODEL_CONFIG = {
    "vocab_size": 256,
    "d_model": 128,
    "n_layers": 4,
    "n_heads": 4,
    "d_ff": 512,
    "max_seq_len": 64,
}


@torch.no_grad()
def _evaluate_heldout_loss(model, dataloader, device) -> float:
    """Mean masked CE loss over the held-out loader."""
    model.eval()
    total_loss = 0.0
    n_batches = 0
    for token_ids, pad_mask, mel in dataloader:
        token_ids = token_ids.to(device)
        pad_mask = pad_mask.to(device)
        mel = mel.to(device).float()
        logits = model(token_ids, mel, key_padding_mask=pad_mask)
        loss = compute_masked_loss(logits, token_ids)
        total_loss += float(loss.item())
        n_batches += 1
    model.train()
    return total_loss / max(n_batches, 1)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Train the Apollo v1 model on a real data/pairs/ corpus."
    )
    parser.add_argument("pairs_root", help="Path to data/pairs/ directory")
    parser.add_argument(
        "--epochs", type=int, default=300,
        help="Number of epochs (D-11, default 300)",
    )
    parser.add_argument(
        "--lr", type=float, default=1e-3,
        help="Peak learning rate (default 1e-3)",
    )
    parser.add_argument(
        "--batch-size", type=int, default=4,
        help="Batch size (default 4)",
    )
    parser.add_argument(
        "--log-every", type=int, default=10,
        help="Log held-out loss every N epochs (D-12, default 10)",
    )
    parser.add_argument(
        "--iteration", type=int, default=1,
        help="Iteration number for checkpoint naming (D-10, default 1)",
    )
    parser.add_argument(
        "--output-dir", type=str, default="models",
        help="Output dir for checkpoints (D-10, default 'models')",
    )
    parser.add_argument(
        "--log-dir", type=str, default="logs",
        help="Output dir for CSV logs (D-12, default 'logs')",
    )
    parser.add_argument(
        "--seed", type=int, default=0,
        help="Random seed (default 0)",
    )
    parser.add_argument(
        "--no-csv", action="store_true",
        help="Disable per-epoch CSV logging",
    )
    args = parser.parse_args(argv)

    try:
        torch.manual_seed(args.seed)

        pairs_root = Path(args.pairs_root)
        if not pairs_root.exists():
            print(f"ERROR: pairs_root does not exist: {pairs_root}", file=sys.stderr)
            return 1

        # 1. Ingest corpus
        artifact = ingest(str(pairs_root))
        n_pairs = artifact["metadata"]["n_pairs"]
        if n_pairs < 30:
            print(
                f"WARNING: corpus has {n_pairs} pair(s); DATA-05 requires >=30 "
                f"for the first real training run. Continuing anyway.",
                file=sys.stderr,
            )

        # 2. Build train / held-out loaders
        train_ds = ApolloDataset(artifact, split="train")
        heldout_ds = ApolloDataset(artifact, split="held_out")
        train_loader = DataLoader(
            train_ds, batch_size=args.batch_size, shuffle=True, collate_fn=collate_fn
        )
        heldout_loader = DataLoader(
            heldout_ds, batch_size=args.batch_size, shuffle=False, collate_fn=collate_fn
        )

        n_train = len(train_ds)
        n_held = len(heldout_ds)

        # 3. Model + optimizer + OneCycleLR (D-09)
        device = get_device()
        model = ApolloModel(**DEFAULT_MODEL_CONFIG).to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)
        steps_per_epoch = max(len(train_loader), 1)
        total_steps = args.epochs * steps_per_epoch
        scheduler = torch.optim.lr_scheduler.OneCycleLR(
            optimizer,
            max_lr=args.lr,
            total_steps=total_steps,
            pct_start=0.05,         # 5% warmup (D-09)
            anneal_strategy="cos",  # cosine decay (D-09)
        )

        # 4. CSV logger setup (D-12)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        csv_writer = None
        csv_file = None
        if not args.no_csv:
            log_dir = Path(args.log_dir)
            log_dir.mkdir(parents=True, exist_ok=True)
            csv_path = log_dir / f"run-{args.iteration:02d}-{timestamp}.csv"
            csv_file = open(csv_path, "w", newline="")
            csv_writer = csv.DictWriter(
                csv_file, fieldnames=["epoch", "train_loss", "held_loss"]
            )
            csv_writer.writeheader()

        # 5. Train loop — do NOT call scheduler.step() here;
        #    train_epoch already steps per-batch (apollo/model/train.py line ~119).
        train_loss = 0.0
        held_loss = float("nan")
        for epoch in range(args.epochs):
            train_loss = train_epoch(
                model, train_loader, optimizer, device, scheduler=scheduler
            )
            if (epoch + 1) % args.log_every == 0 or (epoch + 1) == args.epochs:
                held_loss = _evaluate_heldout_loss(model, heldout_loader, device)
                print(
                    f"epoch {epoch+1}/{args.epochs}  "
                    f"train_loss={train_loss:.4f}  held_loss={held_loss:.4f}"
                )
                if csv_writer is not None:
                    csv_writer.writerow({
                        "epoch": epoch + 1,
                        "train_loss": train_loss,
                        "held_loss": held_loss,
                    })

        if csv_file is not None:
            csv_file.close()

        # 6. Save checkpoint with D-10 naming
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"run-{args.iteration:02d}-{timestamp}.pt"

        training_meta = {
            "n_epochs": args.epochs,
            "n_pairs": n_pairs,
            "final_loss": float(train_loss),
            "type_accuracy": 0.0,  # Phase 3 does not compute type_accuracy
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        save_checkpoint(
            model=model,
            vocab_dict=artifact["vocab"],
            model_config=DEFAULT_MODEL_CONFIG,
            training_meta=training_meta,
            out_path=str(out_path),
        )

        # 7. Final summary
        print(
            f"train done: n_pairs={n_pairs} split=train/held_out={n_train}/{n_held} "
            f"epochs={args.epochs} final_loss={train_loss:.4f} "
            f"held_loss={held_loss:.4f} checkpoint={out_path}"
        )
        return 0

    except IngestError as e:
        print(f"INGEST FAILED: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"UNEXPECTED ERROR: {e!r}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

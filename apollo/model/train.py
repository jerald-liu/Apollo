"""Training loop with response-only masked CE loss (TRAIN-02, TRAIN-03, TRAIN-05).

Plug point for Phase 3: train_epoch accepts scheduler=None (D-16).
Phase 3 will inject a warmup+cosine scheduler without refactoring this module.

RESEARCH-critical fix (pitfall #2):
  Loss mask boundary is `j >= sep_pos` — NOT `j > sep_pos`.
  Using `>` silently drops the first response token from the loss gradient.
  See compute_masked_loss docstring for the full boundary derivation.
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader

from apollo.model.packer import SEP


def get_device() -> torch.device:
    """MPS if available, else CPU (D-19). Never CUDA hard-coded."""
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def compute_masked_loss(
    logits: torch.Tensor,
    token_ids: torch.Tensor,
    sep_id: int = SEP,
) -> torch.Tensor:
    """Masked cross-entropy on response positions only (D-14, D-15, TRAIN-02).

    Shifted prediction: logits[:, :-1] predicts token_ids[:, 1:].
    Position j in shifted space predicts token_ids[j+1] as target.
    We want to score predictions whose TARGET is a response token:
        token_ids[j+1] is a response token
        => j+1 > sep_pos
        => j >= sep_pos        <-- correct boundary (j >= sep_pos, NOT j > sep_pos)

    RESEARCH pitfall #2: using `j > sep_pos` silently drops the first
    response token (token_ids[sep_pos+1]) from the loss. DO NOT use `>`.

    Boundary examples:
        j = sep_pos - 1 : target = SEP          -> EXCLUDED
        j = sep_pos     : target = resp[0]       -> INCLUDED (first response token)
        j = T - 2       : target = EOS           -> INCLUDED

    Args:
        logits:    (B, T, V) — raw model output
        token_ids: (B, T)    — packed token IDs including SEP
        sep_id:    token ID for the SEP token (default: SEP constant from packer)

    Returns:
        Scalar loss tensor with gradient.
    """
    B, T, V = logits.shape
    logits_shifted = logits[:, :-1]               # (B, T-1, V)
    targets_shifted = token_ids[:, 1:]            # (B, T-1)

    # Find first occurrence of sep_id in each sample
    sep_pos = (token_ids == sep_id).long().argmax(dim=1)  # (B,)

    # Build response mask: j >= sep_pos in shifted space
    j_range = torch.arange(T - 1, device=token_ids.device).unsqueeze(0)  # (1, T-1)
    loss_mask = j_range >= sep_pos.unsqueeze(1)   # (B, T-1) — `>=`, NOT `>`

    per_token_loss = F.cross_entropy(
        logits_shifted.reshape(-1, V),
        targets_shifted.reshape(-1),
        reduction="none",
    ).reshape(B, T - 1)

    mask_f = loss_mask.float()
    return (per_token_loss * mask_f).sum() / (mask_f.sum() + 1e-8)


def train_epoch(
    model: nn.Module,
    dataloader: DataLoader,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
    scheduler=None,
) -> float:
    """Run one training epoch. Returns mean batch loss.

    scheduler=None: Phase 2 smoke train uses no LR schedule.
    Phase 3 will pass a warmup+cosine scheduler without refactoring (D-16).

    Gradient clipping at max_norm=1.0 (D-17) prevents early-epoch spikes.
    No mixed precision — float32 throughout (D-18).
    """
    model.train()
    total_loss = 0.0
    n_batches = 0

    for token_ids, pad_mask, mel in dataloader:
        token_ids = token_ids.to(device)
        pad_mask = pad_mask.to(device)
        mel = mel.to(device).float()

        logits = model(token_ids, mel, key_padding_mask=pad_mask)
        loss = compute_masked_loss(logits, token_ids)

        optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)  # D-17
        optimizer.step()
        if scheduler is not None:
            scheduler.step()

        total_loss += loss.item()
        n_batches += 1

    return total_loss / max(n_batches, 1)


def run_training(
    model: nn.Module,
    dataloader: DataLoader,
    *,
    n_epochs: int,
    lr: float = 1e-3,
    device: torch.device | None = None,
) -> dict:
    """Full training loop. Returns {"final_loss": float, "losses": list[float]}.

    TRAIN-03: random init only — does NOT load any checkpoint.
    mel_enc is a submodule of ApolloModel (Plan 02-02), so model.parameters()
    already covers it — no need to instantiate a separate MelEncoder (RESEARCH pitfall #7).
    """
    device = device or get_device()
    model = model.to(device)
    # mel_enc is included in model.parameters() via ApolloModel submodule (D-02, COND-03)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr)

    losses: list[float] = []
    for epoch in range(n_epochs):
        mean_loss = train_epoch(model, dataloader, optimizer, device, scheduler=None)
        losses.append(mean_loss)

    return {"final_loss": losses[-1] if losses else float("nan"), "losses": losses}

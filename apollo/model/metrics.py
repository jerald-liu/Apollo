"""Type-accuracy metric on response positions (TRAIN-04, D-20).

Computes per-token-category accuracy on the response side only.
Uses the same j >= sep_pos boundary as compute_masked_loss in train.py.
"""

from __future__ import annotations

import torch


def token_category(ids: torch.Tensor) -> torch.Tensor:
    """Map token IDs to category indices (D-20).

    0=time_shift [0..31], 1=pitch [32..68], 2=velocity [69..84],
    3=duration [85..108], 4=special [109..111], 5=reserved [112+]
    """
    cat = torch.zeros_like(ids, dtype=torch.long)
    cat = torch.where((ids >= 32) & (ids < 69),   torch.ones_like(ids),           cat)
    cat = torch.where((ids >= 69) & (ids < 85),   torch.full_like(ids, 2),        cat)
    cat = torch.where((ids >= 85) & (ids < 109),  torch.full_like(ids, 3),        cat)
    cat = torch.where((ids >= 109) & (ids < 112), torch.full_like(ids, 4),        cat)
    cat = torch.where(ids >= 112,                  torch.full_like(ids, 5),        cat)
    return cat


def compute_type_accuracy(
    logits: torch.Tensor,
    token_ids: torch.Tensor,
    sep_id: int = 111,
) -> float:
    """Type-accuracy on response positions only.

    Shifted prediction: logits[:, :-1] predicts token_ids[:, 1:].
    Response position in shifted space = j >= sep_pos (same boundary as compute_masked_loss).

    Returns float in [0, 1].
    """
    B, T, V = logits.shape
    preds = logits[:, :-1].argmax(dim=-1)          # (B, T-1)
    targets = token_ids[:, 1:]                      # (B, T-1)

    sep_pos = (token_ids == sep_id).long().argmax(dim=1)    # (B,)
    j_range = torch.arange(T - 1, device=token_ids.device).unsqueeze(0)  # (1, T-1)
    resp_mask = j_range >= sep_pos.unsqueeze(1)             # (B, T-1) — `>=`, NOT `>`

    pred_cats = token_category(preds)
    target_cats = token_category(targets)
    correct = (pred_cats == target_cats) & resp_mask
    return correct.float().sum().item() / (resp_mask.float().sum().item() + 1e-8)

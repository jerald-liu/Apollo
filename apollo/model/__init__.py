"""
apollo.model — Model components for Apollo call-and-response generation.

Phase 2 exports:
    MelEncoder          — CNN mel encoder (D-01); input (B, 1, 96, 128) → output (B, d_model).
    ApolloModel         — decoder-only transformer with MEL prefix injection (Plan 02-02).
    ApolloDataset       — Phase 1 artifact → Dataset, filtered by split (Plan 02-03).
    collate_fn          — Packs [BOS, call, SEP, resp, EOS, PAD...] to MAX_SEQ_LEN=64 (Plan 02-03).
    compute_masked_loss — Response-only masked CE loss (Plan 02-04, TRAIN-02).
    train_epoch         — One training epoch with scheduler plug point (Plan 02-04, D-16).
    run_training        — Full training loop, random init only (Plan 02-04, TRAIN-03).
    get_device          — MPS if available, else CPU (Plan 02-04, D-19).
    token_category      — Token ID → category index mapping (Plan 02-04, D-20).
    compute_type_accuracy — Response-side type-accuracy metric (Plan 02-04, TRAIN-04).
"""

from apollo.model.mel_encoder import MelEncoder
from apollo.model.transformer import ApolloModel
from apollo.model.packer import ApolloDataset, collate_fn, BOS, EOS, SEP, PAD_ID, MAX_SEQ_LEN
from apollo.model.metrics import compute_type_accuracy, token_category
from apollo.model.train import compute_masked_loss, train_epoch, run_training, get_device

__all__ = [
    "MelEncoder",
    "ApolloModel",
    "ApolloDataset",
    "collate_fn",
    "BOS", "EOS", "SEP", "PAD_ID", "MAX_SEQ_LEN",
    "compute_type_accuracy", "token_category",
    "compute_masked_loss", "train_epoch", "run_training", "get_device",
]

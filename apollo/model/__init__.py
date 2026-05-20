"""
apollo.model — Model components for Apollo call-and-response generation.

Phase 2 exports:
    MelEncoder    — CNN mel encoder (D-01); input (B, 1, 96, 128) → output (B, d_model).
    ApolloModel   — decoder-only transformer with MEL prefix injection (Plan 02-02).
    ApolloDataset — Phase 1 artifact → Dataset, filtered by split (Plan 02-03).
    collate_fn    — Packs [BOS, call, SEP, resp, EOS, PAD...] to MAX_SEQ_LEN=64 (Plan 02-03).

Downstream plans will add:
    compute_type_accuracy — response-side type metric (Plan 02-04)
"""

from apollo.model.mel_encoder import MelEncoder
from apollo.model.transformer import ApolloModel
from apollo.model.packer import ApolloDataset, collate_fn, BOS, EOS, SEP, PAD_ID, MAX_SEQ_LEN

__all__ = [
    "MelEncoder",
    "ApolloModel",
    "ApolloDataset",
    "collate_fn",
    "BOS", "EOS", "SEP", "PAD_ID", "MAX_SEQ_LEN",
]

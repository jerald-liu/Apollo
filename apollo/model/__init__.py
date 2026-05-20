"""
apollo.model — Model components for Apollo call-and-response generation.

Phase 2 exports:
    MelEncoder  — CNN mel encoder (D-01); input (B, 1, 96, 128) → output (B, d_model).
    ApolloModel — decoder-only transformer with MEL prefix injection (Plan 02-02).

Downstream plans will add:
    ApolloDataset / collate_fn — data packing (Plan 02-03)
    compute_type_accuracy — response-side type metric (Plan 02-04)
"""

from apollo.model.mel_encoder import MelEncoder
from apollo.model.transformer import ApolloModel

__all__ = ["MelEncoder", "ApolloModel"]

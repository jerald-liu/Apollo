"""
apollo.model — Model components for Apollo call-and-response generation.

Phase 2 exports:
    MelEncoder — CNN mel encoder (D-01); input (B, 1, 96, 128) → output (B, d_model).

Downstream plans will add:
    ApolloModel  — decoder-only transformer (Plan 02-02)
    ApolloDataset / collate_fn — data packing (Plan 02-03)
    compute_type_accuracy — response-side type metric (Plan 02-04)
"""

from apollo.model.mel_encoder import MelEncoder

__all__ = ["MelEncoder"]

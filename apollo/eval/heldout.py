"""Enumerate the deterministic held-out subset of authored pairs.

Used by the Phase-4 grading UI, render-manifest writer, and ship-gate.
Single source of truth for "which pairs are eval-eligible" — composes
apollo.ingest.split.is_heldout (DATA-04) with apollo.ingest.pairs.discover_pairs.

See .planning/phases/04-evaluation-loop/04-RESEARCH.md §"Enumerate held-out pairs"
and CONTEXT.md (Reusable Assets).
"""
from __future__ import annotations

from typing import List

from apollo.ingest.pairs import discover_pairs, PairPath
from apollo.ingest.split import is_heldout


def enumerate_heldout(pairs_root: str) -> List[PairPath]:
    """Return the deterministic held-out subset for `<pairs_root>`."""
    return [p for p in discover_pairs(pairs_root) if is_heldout(p.nnn)]

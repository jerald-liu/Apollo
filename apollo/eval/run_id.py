"""Run identity hash for (checkpoint, training corpus) pairs.

EVAL-03: distinct identity per (model weights, corpus) combination so
scores.jsonl and runs.jsonl can be joined across iterations.

Decisions:
- D-09: auto-derived from checkpoint bytes + sorted training pair-IDs.
  No manual tagging.

Returns a 16-hex-character blake2b-8 digest. 64-bit collision space is
sufficient for realistic iteration counts (<1000 runs) per RESEARCH A7.

See .planning/phases/04-evaluation-loop/04-RESEARCH.md §Pattern 2.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable


def compute_run_id(checkpoint_path: str, train_pair_ids: Iterable[str]) -> str:
    """Stable 16-char hash of (checkpoint bytes, sorted training pair-IDs).

    Reads the checkpoint in 64 KiB chunks (multi-MB checkpoints stay out of RAM).
    Same (ckpt file, corpus) → same run_id, deterministic across platforms.

    Args:
        checkpoint_path: path to the .pt file produced by Phase 2/3 training.
        train_pair_ids: iterable of zero-padded pair IDs ("001", "002", ...).
                        Internally sorted; order of caller does not matter.

    Returns:
        16-character lowercase hex string.
    """
    h = hashlib.blake2b(digest_size=8)
    p = Path(checkpoint_path)
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    # Delimiter prevents pair-ID suffix collisions with checkpoint tail bytes.
    h.update(b"\x00CORPUS\x00")
    for pid in sorted(train_pair_ids):
        h.update(pid.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()

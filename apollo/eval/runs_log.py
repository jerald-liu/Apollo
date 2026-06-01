"""Append-only JSONL run manifest (EVAL-03).

One record per training run. The `iteration: true` flag (D-16) is what the
ship-gate (EVAL-05) uses to identify gate-eligible runs.

Schema (Claude's discretion per D-08 — minimums per CONTEXT):
    - run_id              (str, 16-hex from compute_run_id)
    - created             (ISO-UTC, auto-filled if absent)
    - checkpoint_path     (str)
    - checkpoint_hash     (str, sha256 of checkpoint bytes — distinct from
                           run_id which is blake2b-8 over bytes + pair_ids)
    - train_pair_ids      (list[str], sorted)
    - n_train_pairs       (int)
    - n_heldout_pairs     (int)
    - iteration           (bool)
    - iteration_label     (str, optional human label)
    - git_sha             (str, optional)
    - notes               (str, default "")

See .planning/phases/04-evaluation-loop/04-RESEARCH.md §"Recommended `runs.jsonl` record schema".
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def append_run(record: dict, path: str = "eval/runs.jsonl") -> None:
    """Append one run record. Auto-fills `created` if absent."""
    record = dict(record)  # don't mutate caller's dict
    record.setdefault(
        "created",
        datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, separators=(",", ":")) + "\n")
        f.flush()

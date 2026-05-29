"""Append-only JSONL score store for held-out grading sessions (EVAL-03).

Decisions:
- D-08: JSONL, one record per (run, pair, dim) at `eval/scores.jsonl`.
        Append-only, git-diffable, no schema migrations.

Per-line POSIX append atomicity is the durability guarantee for crash mid-
session. `append_score_pair` writes BOTH dim lines from a single open() call
to avoid the half-submit hazard described in RESEARCH §Pitfall 2.

Last-write-wins on read: when the same (run_id, pair_id, dim) appears twice,
`load_scores` returns both records in file order; consumers take the last.

See .planning/phases/04-evaluation-loop/04-RESEARCH.md §Pattern 1.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List

_VALID_DIMS = {"fit", "coherence"}


def _build_record(run_id: str, pair_id: str, dim: str, score: int,
                  note: str = "") -> dict:
    assert dim in _VALID_DIMS, f"unknown dim {dim!r}"
    assert 1 <= score <= 5, f"score {score} outside 1..5"
    return {
        "run_id": run_id,
        "pair_id": pair_id,
        "dim": dim,
        "score": score,
        "note": note,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def append_score(run_id: str, pair_id: str, dim: str, score: int,
                 note: str = "", path: str = "eval/scores.jsonl") -> None:
    """Append one (run_id, pair_id, dim) score record."""
    record = _build_record(run_id, pair_id, dim, score, note)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, separators=(",", ":")) + "\n")
        f.flush()


def append_score_pair(run_id: str, pair_id: str, fit: int, coherence: int,
                      note: str = "", path: str = "eval/scores.jsonl") -> None:
    """Append both fit + coherence in ONE open() — avoids Pitfall 2 half-submit.

    Note attaches to the `fit` record only; coherence note is empty by
    convention (the rubric treats the note as overall-pair freeform, D-03).
    """
    fit_rec = _build_record(run_id, pair_id, "fit", fit, note)
    coh_rec = _build_record(run_id, pair_id, "coherence", coherence, "")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(fit_rec, separators=(",", ":")) + "\n")
        f.write(json.dumps(coh_rec, separators=(",", ":")) + "\n")
        f.flush()


def load_scores(run_id: str | None = None,
                path: str = "eval/scores.jsonl") -> List[dict]:
    """Return all score records (optionally filtered to one run_id).

    Returns [] when the file does not exist (first-run case, Pitfall 7).
    """
    if not Path(path).is_file():
        return []
    with open(path, encoding="utf-8") as f:
        recs = [json.loads(line) for line in f if line.strip()]
    if run_id is not None:
        recs = [r for r in recs if r["run_id"] == run_id]
    return recs

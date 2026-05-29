"""Ship-gate decision for the active-learning loop (EVAL-05).

Pure function over `eval/runs.jsonl` + `eval/scores.jsonl`. CI-testable; no I/O
beyond reading those two files.

Decisions:
- D-14: improvement = mean call-response-fit strictly up between designated runs.
        "Up by any ε" → strict `>` (exact tie does NOT count).
- D-15: no per-pair regression tolerance — mean is the gate; per-pair trajectories
        live in delta.ipynb.
- D-16: only runs flagged `iteration: true` are gate-eligible.
- D-17: caller (apollo/scripts/eval_ship_check.py) translates (passed, banner)
        into exit-code 0/1.

Predecessor semantics (RESEARCH A2 — confirm with user at plan-check):
Each iteration-marked run's delta is computed vs the row IMMEDIATELY PRECEDING
it in runs.jsonl order, which may itself be a non-iteration run. Alternative
reading ("previous iteration-marked run") is documented in the assumptions
block of 04-02-PLAN.md and can be swapped here if the user confirms.

See .planning/phases/04-evaluation-loop/04-RESEARCH.md §Pattern 5.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import List, Optional, Tuple


def _load_jsonl(path: str) -> List[dict]:
    p = Path(path)
    if not p.is_file():
        return []
    out: List[dict] = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                out.append(json.loads(line))
    return out


def _latest_scores_per_run(scores: List[dict]) -> dict:
    """Reduce score records to last-write-wins per (run_id, pair_id, dim).

    Returns: {(run_id, pair_id, dim): score_int}
    """
    latest: dict = {}
    for s in scores:
        key = (s["run_id"], s["pair_id"], s["dim"])
        latest[key] = s["score"]
    return latest


def _mean_fit(run_id: str, latest: dict) -> float:
    """Mean of last-write-wins fit scores for run_id. NaN if none."""
    vals = [v for (rid, _pid, dim), v in latest.items()
            if rid == run_id and dim == "fit"]
    if not vals:
        return math.nan
    return sum(vals) / len(vals)


def check_ship_gate(runs_path: str, scores_path: str) -> Tuple[bool, str]:
    """Return (passed, banner) for the v1 ship-gate.

    Pass iff the last two iteration-marked runs each have mean call-response
    fit strictly greater than the row immediately preceding them in
    runs.jsonl order.
    """
    runs = _load_jsonl(runs_path)
    if not runs:
        return False, "Ship-gate FAIL — no runs recorded; nothing to check."

    latest = _latest_scores_per_run(_load_jsonl(scores_path))

    iter_indices = [i for i, r in enumerate(runs) if r.get("iteration") is True]
    if len(iter_indices) < 2:
        return False, (
            f"Ship-gate FAIL — need ≥2 iteration-marked runs; "
            f"have {len(iter_indices)}."
        )

    # Last two iteration-marked runs
    last_two = iter_indices[-2:]

    deltas = []
    pairs: list[tuple[str, str, float]] = []  # (cur8, pred8, delta)
    for idx in last_two:
        cur = runs[idx]
        cur_id = cur["run_id"]
        if idx == 0:
            return False, (
                f"Ship-gate FAIL — run {cur_id[:8]} has no predecessor; "
                f"cannot compute delta."
            )
        pred = runs[idx - 1]
        pred_id = pred["run_id"]
        cur_mean = _mean_fit(cur_id, latest)
        pred_mean = _mean_fit(pred_id, latest)
        if math.isnan(cur_mean):
            return False, (
                f"Ship-gate FAIL — run {cur_id[:8]} has no fit scores recorded."
            )
        if math.isnan(pred_mean):
            return False, (
                f"Ship-gate FAIL — run {pred_id[:8]} has no fit scores recorded."
            )
        d = cur_mean - pred_mean
        deltas.append(d)
        pairs.append((cur_id[:8], pred_id[:8], d))

    both_up = all(d > 0 for d in deltas)  # strict — D-14
    if both_up:
        lines = [
            f"  {cur8} vs {pred8}: Δ mean fit = {d:+.3f}"
            for (cur8, pred8, d) in pairs
        ]
        banner = "Ship-gate PASS — last two iteration runs:\n" + "\n".join(lines)
        return True, banner

    lines = [
        f"  {cur8} vs {pred8}: Δ mean fit = {d:+.3f}"
        for (cur8, pred8, d) in pairs
    ]
    banner = "Ship-gate FAIL — improvement not sustained:\n" + "\n".join(lines)
    return False, banner

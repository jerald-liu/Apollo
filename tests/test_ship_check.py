"""Tests for check_ship_gate logic (EVAL-05, D-14..D-17).

Synthetic runs.jsonl + scores.jsonl fixtures cover every branch of the gate.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from apollo.eval.ship_check import check_ship_gate


def _write_runs(path: Path, runs: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in runs:
            f.write(json.dumps(r) + "\n")


def _write_scores(path: Path, scores: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for s in scores:
            f.write(json.dumps(s) + "\n")


def _fit(run_id: str, pair_id: str, score: int) -> dict:
    return {"run_id": run_id, "pair_id": pair_id, "dim": "fit", "score": score}


def test_empty_runs_fails(tmp_path):
    runs = tmp_path / "runs.jsonl"
    scores = tmp_path / "scores.jsonl"
    runs.touch(); scores.touch()
    passed, msg = check_ship_gate(str(runs), str(scores))
    assert not passed
    assert "no runs" in msg.lower() or "need" in msg.lower()


def test_missing_files_fails(tmp_path):
    passed, msg = check_ship_gate(str(tmp_path / "runs.jsonl"),
                                   str(tmp_path / "scores.jsonl"))
    assert not passed


def test_one_iteration_run_fails(tmp_path):
    runs = tmp_path / "runs.jsonl"
    scores = tmp_path / "scores.jsonl"
    _write_runs(runs, [
        {"run_id": "r0_first", "iteration": False},
        {"run_id": "r1_only_iter", "iteration": True},
    ])
    _write_scores(scores, [_fit("r1_only_iter", "001", 4)])
    passed, msg = check_ship_gate(str(runs), str(scores))
    assert not passed
    assert "2 iteration" in msg or "≥2" in msg


def test_two_iterations_both_improve_passes(tmp_path):
    runs = tmp_path / "runs.jsonl"
    scores = tmp_path / "scores.jsonl"
    _write_runs(runs, [
        {"run_id": "r0_base", "iteration": False},
        {"run_id": "r1_iter", "iteration": True},   # predecessor: r0_base
        {"run_id": "r2_base", "iteration": False},
        {"run_id": "r3_iter", "iteration": True},   # predecessor: r2_base
    ])
    _write_scores(scores, [
        _fit("r0_base", "001", 2), _fit("r0_base", "002", 2),
        _fit("r1_iter", "001", 3), _fit("r1_iter", "002", 3),  # +1.0 vs r0
        _fit("r2_base", "001", 3), _fit("r2_base", "002", 3),
        _fit("r3_iter", "001", 4), _fit("r3_iter", "002", 4),  # +1.0 vs r2
    ])
    passed, banner = check_ship_gate(str(runs), str(scores))
    assert passed, banner
    assert "PASS" in banner
    assert "+1.000" in banner


def test_tie_fails(tmp_path):
    """D-14: 'up by any ε' — exact tie is NOT improvement."""
    runs = tmp_path / "runs.jsonl"
    scores = tmp_path / "scores.jsonl"
    _write_runs(runs, [
        {"run_id": "r0", "iteration": False},
        {"run_id": "r1", "iteration": True},
        {"run_id": "r2", "iteration": False},
        {"run_id": "r3", "iteration": True},
    ])
    _write_scores(scores, [
        _fit("r0", "001", 3),
        _fit("r1", "001", 3),  # tie — Δ=0
        _fit("r2", "001", 3),
        _fit("r3", "001", 4),  # +1.0
    ])
    passed, _ = check_ship_gate(str(runs), str(scores))
    assert not passed


def test_regression_fails(tmp_path):
    runs = tmp_path / "runs.jsonl"
    scores = tmp_path / "scores.jsonl"
    _write_runs(runs, [
        {"run_id": "r0", "iteration": False},
        {"run_id": "r1", "iteration": True},
        {"run_id": "r2", "iteration": False},
        {"run_id": "r3", "iteration": True},
    ])
    _write_scores(scores, [
        _fit("r0", "001", 3),
        _fit("r1", "001", 4),  # +1.0
        _fit("r2", "001", 4),
        _fit("r3", "001", 3),  # -1.0
    ])
    passed, _ = check_ship_gate(str(runs), str(scores))
    assert not passed


def test_non_iteration_runs_used_as_predecessors(tmp_path):
    """A2: predecessor = immediately previous row in runs.jsonl (may be non-iter)."""
    runs = tmp_path / "runs.jsonl"
    scores = tmp_path / "scores.jsonl"
    _write_runs(runs, [
        {"run_id": "sweep0", "iteration": False},  # exploratory sweep
        {"run_id": "iter1",  "iteration": True},
        {"run_id": "sweep1", "iteration": False},
        {"run_id": "iter2",  "iteration": True},
    ])
    _write_scores(scores, [
        _fit("sweep0", "001", 2),
        _fit("iter1",  "001", 3),  # +1 vs sweep0
        _fit("sweep1", "001", 3),
        _fit("iter2",  "001", 4),  # +1 vs sweep1
    ])
    passed, banner = check_ship_gate(str(runs), str(scores))
    assert passed
    assert "iter1"[:8] in banner or "iter1" in banner


def test_coherence_ignored_by_gate(tmp_path):
    """D-14: coherence is tracked, not gating."""
    runs = tmp_path / "runs.jsonl"
    scores = tmp_path / "scores.jsonl"
    _write_runs(runs, [
        {"run_id": "r0", "iteration": False},
        {"run_id": "r1", "iteration": True},
        {"run_id": "r2", "iteration": False},
        {"run_id": "r3", "iteration": True},
    ])
    # Fit improves; coherence regresses. Gate must still PASS.
    _write_scores(scores, [
        _fit("r0", "001", 2),
        {"run_id": "r0", "pair_id": "001", "dim": "coherence", "score": 5},
        _fit("r1", "001", 3),
        {"run_id": "r1", "pair_id": "001", "dim": "coherence", "score": 1},
        _fit("r2", "001", 3),
        {"run_id": "r2", "pair_id": "001", "dim": "coherence", "score": 5},
        _fit("r3", "001", 4),
        {"run_id": "r3", "pair_id": "001", "dim": "coherence", "score": 1},
    ])
    passed, _ = check_ship_gate(str(runs), str(scores))
    assert passed


def test_last_write_wins_on_dup_scores(tmp_path):
    runs = tmp_path / "runs.jsonl"
    scores = tmp_path / "scores.jsonl"
    _write_runs(runs, [
        {"run_id": "r0", "iteration": False},
        {"run_id": "r1", "iteration": True},
        {"run_id": "r2", "iteration": False},
        {"run_id": "r3", "iteration": True},
    ])
    _write_scores(scores, [
        _fit("r0", "001", 2),
        _fit("r1", "001", 2),  # initial re-grade
        _fit("r1", "001", 4),  # corrected — this is what counts
        _fit("r2", "001", 3),
        _fit("r3", "001", 5),
    ])
    passed, _ = check_ship_gate(str(runs), str(scores))
    assert passed  # r1 effective fit = 4 (last write), beats r0 (2); r3=5 beats r2=3

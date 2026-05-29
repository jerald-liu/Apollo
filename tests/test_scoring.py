"""Tests for scores_log + runs_log append/load round-trip (EVAL-03, D-08).

Pins the JSONL append-only contract: same (run, pair, dim) appends another
line (no mutation); atomic two-dim submit; load_scores filtering; empty-file
safety.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from apollo.eval.scores_log import append_score, append_score_pair, load_scores
from apollo.eval.runs_log import append_run


def test_append_then_load_round_trip(tmp_path):
    path = str(tmp_path / "scores.jsonl")
    append_score("r1", "001", "fit", 4, "note-a", path=path)
    recs = load_scores(path=path)
    assert len(recs) == 1
    assert recs[0]["run_id"] == "r1"
    assert recs[0]["pair_id"] == "001"
    assert recs[0]["dim"] == "fit"
    assert recs[0]["score"] == 4
    assert recs[0]["note"] == "note-a"
    assert "ts" in recs[0]


def test_load_scores_empty_when_file_missing(tmp_path):
    # Pitfall 7
    assert load_scores(path=str(tmp_path / "does-not-exist.jsonl")) == []


def test_append_score_pair_writes_both_dims(tmp_path):
    path = str(tmp_path / "scores.jsonl")
    append_score_pair("r1", "001", fit=4, coherence=3, note="x", path=path)
    recs = load_scores(path=path)
    assert len(recs) == 2
    dims = {r["dim"] for r in recs}
    assert dims == {"fit", "coherence"}


def test_append_score_pair_atomic_one_open(tmp_path):
    """Both lines from one open(). Verifiable: file written once contains 2 lines."""
    path = tmp_path / "scores.jsonl"
    append_score_pair("r1", "001", fit=4, coherence=3, path=str(path))
    lines = path.read_text().splitlines()
    assert len(lines) == 2
    assert all(json.loads(l)["run_id"] == "r1" for l in lines)


def test_load_scores_filters_by_run_id(tmp_path):
    path = str(tmp_path / "scores.jsonl")
    append_score("r1", "001", "fit", 4, path=path)
    append_score("r2", "001", "fit", 5, path=path)
    append_score("r1", "002", "fit", 3, path=path)
    only_r1 = load_scores(run_id="r1", path=path)
    assert len(only_r1) == 2
    assert all(r["run_id"] == "r1" for r in only_r1)


def test_re_submit_appends_no_mutation(tmp_path):
    path = str(tmp_path / "scores.jsonl")
    append_score("r1", "001", "fit", 2, path=path)
    append_score("r1", "001", "fit", 5, path=path)  # corrected score
    recs = load_scores(path=path)
    assert len(recs) == 2  # both lines present; consumer takes last
    assert recs[-1]["score"] == 5


def test_invalid_dim_raises(tmp_path):
    with pytest.raises(AssertionError):
        append_score("r1", "001", "vibes", 4, path=str(tmp_path / "x.jsonl"))


def test_out_of_range_score_raises(tmp_path):
    with pytest.raises(AssertionError):
        append_score("r1", "001", "fit", 0, path=str(tmp_path / "x.jsonl"))
    with pytest.raises(AssertionError):
        append_score("r1", "001", "fit", 6, path=str(tmp_path / "x.jsonl"))


def test_append_run_autofills_created(tmp_path):
    path = tmp_path / "runs.jsonl"
    append_run({"run_id": "r1", "checkpoint_path": "models/r1.pt",
                "train_pair_ids": ["001"], "iteration": True}, path=str(path))
    rec = json.loads(path.read_text().splitlines()[0])
    assert rec["run_id"] == "r1"
    assert rec["iteration"] is True
    assert "created" in rec
    assert rec["created"].endswith("+00:00")  # ISO UTC with offset


def test_append_run_preserves_caller_created(tmp_path):
    path = tmp_path / "runs.jsonl"
    append_run({"run_id": "r1", "created": "2026-01-01T00:00:00+00:00",
                "iteration": False}, path=str(path))
    rec = json.loads(path.read_text().splitlines()[0])
    assert rec["created"] == "2026-01-01T00:00:00+00:00"


def test_runs_log_does_not_mutate_caller_record(tmp_path):
    path = tmp_path / "runs.jsonl"
    caller_rec = {"run_id": "r1", "iteration": True}
    append_run(caller_rec, path=str(path))
    assert "created" not in caller_rec  # function copied, didn't mutate

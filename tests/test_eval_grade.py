"""Tests for the eval_grade CLI launcher (WR-02).

Patches Flask.run so main() returns without binding a port.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from apollo.scripts import eval_grade


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Build a pairs_root + runs.jsonl with one matching run record."""
    from apollo.ingest import synthesize_pair
    pairs_root = tmp_path / "pairs"
    pairs_root.mkdir()
    for i in range(3):
        synthesize_pair(pairs_root, nnn=f"{i:03d}")
    runs_path = tmp_path / "runs.jsonl"
    runs_path.write_text(json.dumps({
        "run_id": "abcdef1234567890",
        "checkpoint_path": "models/fake.pt",
        "iteration": True,
    }) + "\n")
    scores_path = tmp_path / "scores.jsonl"
    # Stub Flask.run so main() doesn't block on a port.
    monkeypatch.setattr("flask.Flask.run", lambda *a, **kw: None)
    return {
        "pairs_root": str(pairs_root),
        "runs_path": str(runs_path),
        "scores_path": str(scores_path),
    }


def test_main_prints_banner(env, capsys):
    rc = eval_grade.main([
        env["pairs_root"], "--run-id", "abcdef1234567890",
        "--runs-path", env["runs_path"], "--scores-path", env["scores_path"],
        "--port", "5050",
    ])
    assert rc == 0
    err = capsys.readouterr().err
    assert "http://127.0.0.1:5050/" in err
    assert "run_id=abcdef12" in err


def test_main_warns_on_unknown_run_id(env, capsys):
    rc = eval_grade.main([
        env["pairs_root"], "--run-id", "ghosthashghosthsh",
        "--runs-path", env["runs_path"], "--scores-path", env["scores_path"],
    ])
    assert rc == 0
    err = capsys.readouterr().err
    assert "not found" in err
    assert "ghosthashghosthsh" in err


def test_main_no_warning_when_run_id_present(env, capsys):
    rc = eval_grade.main([
        env["pairs_root"], "--run-id", "abcdef1234567890",
        "--runs-path", env["runs_path"], "--scores-path", env["scores_path"],
    ])
    assert rc == 0
    err = capsys.readouterr().err
    assert "not found" not in err

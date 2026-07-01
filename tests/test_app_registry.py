"""Tests for apollo.app.registry — append-only run registry + ACTIVE pointer.

Uses tmp_path (pytest fixture) as models_dir; no real training, no subprocess.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from apollo.app import registry as R


# ------------------------------------------------------------------ helpers

def _make_pair(pairs_root: Path, name: str, *, with_response: bool = False) -> Path:
    """Create a minimal pair directory with required files."""
    d = pairs_root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "call.mid").write_bytes(b"\x00\x01" + name.encode())
    (d / "call_fm.json").write_bytes(b'{"spec_version": "1.0"}')
    if with_response:
        (d / "response.mid").write_bytes(b"\x02\x03")
    return d


# ------------------------------------------------------------------ tests

def test_append_and_list_newest_first(tmp_path):
    """Two appended rows come back newest-first from list_runs()."""
    R.append_run(
        tmp_path,
        checkpoint="run-01-A.pt",
        iteration=1,
        corpus_pair_count=3,
        corpus_hash="abc",
        held_loss=0.5,
        train_loss=0.4,
        timestamp="2026-01-01T00:00:00Z",
    )
    R.append_run(
        tmp_path,
        checkpoint="run-01-B.pt",
        iteration=1,
        corpus_pair_count=4,
        corpus_hash="def",
        held_loss=0.3,
        train_loss=0.2,
        timestamp="2026-01-02T00:00:00Z",
    )
    rows = R.list_runs(tmp_path)
    assert len(rows) == 2
    assert rows[0]["checkpoint"] == "run-01-B.pt"   # newest first
    assert rows[1]["checkpoint"] == "run-01-A.pt"
    # Required fields present
    assert rows[0]["corpus_hash"] == "def"
    assert rows[0]["held_loss"] == pytest.approx(0.3)


def test_checkpoint_stored_as_basename(tmp_path):
    """append_run strips directory components from the checkpoint arg."""
    R.append_run(
        tmp_path,
        checkpoint="/abs/models/run-01-T.pt",
        iteration=1,
        corpus_pair_count=2,
        corpus_hash="xxx",
        held_loss=None,
        train_loss=None,
    )
    rows = R.list_runs(tmp_path)
    assert len(rows) == 1
    assert rows[0]["checkpoint"] == "run-01-T.pt"
    assert "/" not in rows[0]["checkpoint"]


def test_corpus_hash_deterministic(tmp_path):
    """Hash is stable across calls and changes when a file changes."""
    pairs_root = tmp_path / "pairs"
    _make_pair(pairs_root, "001")
    _make_pair(pairs_root, "002", with_response=True)

    h1 = R.compute_corpus_hash(pairs_root)
    h2 = R.compute_corpus_hash(pairs_root)
    assert h1 == h2, "hash must be deterministic across two calls"
    assert len(h1) == 64, "sha256 hex digest should be 64 chars"

    # Mutate call.mid in 001 → hash must change.
    (pairs_root / "001" / "call.mid").write_bytes(b"\xFF\xFE different bytes")
    h3 = R.compute_corpus_hash(pairs_root)
    assert h3 != h1, "hash must change when corpus content changes"


def test_active_pointer_roundtrip(tmp_path):
    """get_active / set_active / clear_active round-trip correctly."""
    assert R.get_active(tmp_path) is None         # absent → None

    R.set_active(tmp_path, "run-02-T.pt")
    assert R.get_active(tmp_path) == "run-02-T.pt"

    R.clear_active(tmp_path)
    assert R.get_active(tmp_path) is None          # cleared → None


def test_list_runs_skips_corrupt_line(tmp_path):
    """Corrupt lines in runs.jsonl are silently skipped; valid rows returned."""
    runs_file = tmp_path / "runs.jsonl"
    valid_row = {
        "checkpoint": "run-01-X.pt",
        "timestamp": "2026-01-01T00:00:00Z",
        "iteration": 1,
        "corpus_pair_count": 5,
        "corpus_hash": "aaa",
        "held_loss": 0.42,
        "train_loss": 0.38,
    }
    runs_file.write_text(
        json.dumps(valid_row) + "\n"
        + "THIS IS NOT JSON!!! ###\n",
        encoding="utf-8",
    )
    rows = R.list_runs(tmp_path)
    assert len(rows) == 1, f"Expected 1 valid row, got {rows}"
    assert rows[0]["checkpoint"] == "run-01-X.pt"


def test_list_runs_empty_when_no_file(tmp_path):
    """list_runs returns [] when runs.jsonl does not exist."""
    assert R.list_runs(tmp_path) == []


def test_corpus_hash_empty_corpus(tmp_path):
    """Empty corpus (no valid pairs) → stable (non-crashing) hex digest."""
    pairs_root = tmp_path / "empty_pairs"
    pairs_root.mkdir()
    h = R.compute_corpus_hash(pairs_root)
    assert isinstance(h, str) and len(h) == 64


def test_corpus_hash_ignores_invalid_pairs(tmp_path):
    """Dirs without call.mid + call_fm.json are excluded from the hash."""
    pairs_root = tmp_path / "pairs"
    # Create one valid pair and one dir that is missing call_fm.json.
    _make_pair(pairs_root, "001")
    bad = pairs_root / "002"
    bad.mkdir()
    (bad / "call.mid").write_bytes(b"\x00\x00")   # missing call_fm.json

    h_with_bad = R.compute_corpus_hash(pairs_root)
    # Remove the bad dir entirely — hash should be same.
    import shutil
    shutil.rmtree(bad)
    h_without = R.compute_corpus_hash(pairs_root)
    assert h_with_bad == h_without

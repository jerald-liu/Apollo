"""Tests for apollo/scripts/train.py — production training CLI."""
from __future__ import annotations

from pathlib import Path

import pytest

import apollo.scripts.train as train_script
from apollo.ingest.mock import synthesize_pair


def _make_pairs(root: Path, n: int) -> None:
    """Synthesize n mock pairs under root/NNN/."""
    root.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        synthesize_pair(root, nnn=f"{i:03d}")


def test_train_cli_smoke_creates_checkpoint(tmp_path):
    pairs_root = tmp_path / "pairs"
    _make_pairs(pairs_root, 7)  # 7 pairs: 6 train + 1 held_out (nnn=006 is heldout)
    rc = train_script.main([
        str(pairs_root),
        "--epochs", "3",
        "--iteration", "1",
        "--output-dir", str(tmp_path / "models"),
        "--log-dir", str(tmp_path / "logs"),
        "--no-csv",
    ])
    assert rc == 0, f"train.main returned {rc}"
    checkpoints = list((tmp_path / "models").glob("run-01-*.pt"))
    assert len(checkpoints) == 1
    assert checkpoints[0].name.startswith("run-01-")
    assert checkpoints[0].name.endswith(".pt")


def test_train_cli_logs_held_out(tmp_path, capsys):
    pairs_root = tmp_path / "pairs"
    _make_pairs(pairs_root, 7)
    rc = train_script.main([
        str(pairs_root),
        "--epochs", "2",
        "--log-every", "1",
        "--iteration", "1",
        "--output-dir", str(tmp_path / "models"),
        "--no-csv",
    ])
    assert rc == 0
    captured = capsys.readouterr()
    assert "held_loss=" in captured.out
    assert "train_loss=" in captured.out


def test_train_cli_iteration_naming(tmp_path):
    pairs_root = tmp_path / "pairs"
    _make_pairs(pairs_root, 7)
    rc = train_script.main([
        str(pairs_root),
        "--epochs", "2",
        "--iteration", "5",
        "--output-dir", str(tmp_path / "models"),
        "--no-csv",
    ])
    assert rc == 0
    checkpoints = list((tmp_path / "models").glob("run-05-*.pt"))
    assert len(checkpoints) == 1, (
        f"expected one run-05-*.pt; found "
        f"{[c.name for c in (tmp_path / 'models').iterdir()]}"
    )


def test_train_cli_warns_on_small_corpus(tmp_path, capsys):
    pairs_root = tmp_path / "pairs"
    _make_pairs(pairs_root, 7)  # 7 < 30 triggers DATA-05 warning
    rc = train_script.main([
        str(pairs_root),
        "--epochs", "1",
        "--iteration", "1",
        "--output-dir", str(tmp_path / "models"),
        "--no-csv",
    ])
    assert rc == 0
    captured = capsys.readouterr()
    assert "WARNING" in captured.err
    assert "30" in captured.err


def test_train_cli_no_csv_flag(tmp_path):
    pairs_root = tmp_path / "pairs"
    _make_pairs(pairs_root, 7)
    log_dir = tmp_path / "logs"
    rc = train_script.main([
        str(pairs_root),
        "--epochs", "2",
        "--iteration", "1",
        "--output-dir", str(tmp_path / "models"),
        "--log-dir", str(log_dir),
        "--no-csv",
    ])
    assert rc == 0
    csvs = list(log_dir.glob("*.csv")) if log_dir.exists() else []
    assert len(csvs) == 0, f"expected no CSV; found {csvs}"

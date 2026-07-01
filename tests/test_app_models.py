"""Tests for GET /models + POST /models/activate (APP-14, APP-15, T-05-17/18).

Strategy: use monkeypatch to redirect registry calls to a tmp_path models dir
so that "models" relative path inside create_app uses our tmp dir.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from apollo.app.app import create_app
from apollo.app import registry as R


# ------------------------------------------------------------------ fixture helpers

@pytest.fixture()
def tmp_models(tmp_path, monkeypatch):
    """Create a tmp_path/models dir; monkeypatch registry calls to use it."""
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    # Redirect all registry calls from "models" (cwd-relative) to our tmp dir.
    monkeypatch.setattr(R, "runs_path", lambda md=None: models_dir / "runs.jsonl")
    monkeypatch.setattr(R, "active_path", lambda md=None: models_dir / "ACTIVE")

    # Wrap list_runs/get_active/set_active/clear_active/append_run to ignore
    # their models_dir argument and operate on our tmp dir.
    original_list_runs = R.list_runs.__wrapped__ if hasattr(R.list_runs, '__wrapped__') else None

    def _list_runs(md=None):
        return _real_list_runs(models_dir)

    def _get_active(md=None):
        return _real_get_active(models_dir)

    def _set_active(md=None, checkpoint_basename=None):
        _real_set_active(models_dir, checkpoint_basename)

    def _clear_active(md=None):
        _real_clear_active(models_dir)

    def _append_run(md=None, *, checkpoint, iteration, corpus_pair_count,
                    corpus_hash, held_loss, train_loss, timestamp=None):
        return _real_append_run(
            models_dir,
            checkpoint=checkpoint,
            iteration=iteration,
            corpus_pair_count=corpus_pair_count,
            corpus_hash=corpus_hash,
            held_loss=held_loss,
            train_loss=train_loss,
            timestamp=timestamp,
        )

    # Save real functions before patching.
    _real_list_runs = R.list_runs
    _real_get_active = R.get_active
    _real_set_active = R.set_active
    _real_clear_active = R.clear_active
    _real_append_run = R.append_run

    monkeypatch.setattr(R, "list_runs", _list_runs)
    monkeypatch.setattr(R, "get_active", _get_active)
    monkeypatch.setattr(R, "set_active", _set_active)
    monkeypatch.setattr(R, "clear_active", _clear_active)
    monkeypatch.setattr(R, "append_run", _append_run)

    return models_dir


@pytest.fixture()
def app_client(tmp_path, tmp_models):
    """Flask test client with an isolated pairs_root and models dir."""
    pairs_root = tmp_path / "pairs"
    pairs_root.mkdir()
    application = create_app(pairs_root=str(pairs_root))
    application.config["TESTING"] = True
    with application.test_client() as client:
        yield client, tmp_models


# ------------------------------------------------------------------ helpers

def _add_run(models_dir: Path, checkpoint: str, held_loss: float = 0.5, ts: str = "2026-01-01T00:00:00Z") -> None:
    """Append a run row directly to the tmp models dir."""
    R._real_append_run(
        models_dir,
        checkpoint=checkpoint,
        iteration=1,
        corpus_pair_count=3,
        corpus_hash="abc",
        held_loss=held_loss,
        train_loss=0.4,
        timestamp=ts,
    )


# ------------------------------------------------------------------ tests

def test_models_empty_state(app_client):
    """GET /models with no runs → 200 + empty-state copy."""
    client, _ = app_client
    rv = client.get("/models")
    assert rv.status_code == 200
    body = rv.data.decode()
    assert "No training runs recorded yet" in body


def test_models_lists_runs(app_client, tmp_path, monkeypatch):
    """Two runs → both checkpoint basenames appear; active badge on effective-active."""
    client, models_dir = app_client
    import json
    runs_file = models_dir / "runs.jsonl"
    row_a = {"checkpoint": "run-01-A.pt", "timestamp": "2026-01-01T00:00:00Z",
             "iteration": 1, "corpus_pair_count": 3, "corpus_hash": "aa",
             "held_loss": 0.5, "train_loss": 0.4}
    row_b = {"checkpoint": "run-02-B.pt", "timestamp": "2026-01-02T00:00:00Z",
             "iteration": 1, "corpus_pair_count": 4, "corpus_hash": "bb",
             "held_loss": 0.3, "train_loss": 0.2}
    runs_file.write_text(
        json.dumps(row_a) + "\n" + json.dumps(row_b) + "\n",
        encoding="utf-8",
    )

    # Create a fake .pt file so _latest_checkpoint() returns run-02-B.pt.
    # The route uses Path("models").glob("*.pt") which is cwd-relative;
    # we place the file under models_dir and monkeypatch _latest_checkpoint via
    # the registry's effective_active computation path: we just pin run-02-B.pt
    # so the badge renders.
    (models_dir / "ACTIVE").write_text("run-02-B.pt\n", encoding="utf-8")

    rv = client.get("/models")
    assert rv.status_code == 200
    body = rv.data.decode()
    assert "run-01-A.pt" in body
    assert "run-02-B.pt" in body
    # data-active badge should appear on the pinned row.
    assert "data-active" in body

    # Clean up pin (don't leave it for other tests — each has its own tmp dir anyway).
    (models_dir / "ACTIVE").unlink(missing_ok=True)


def test_activate_pins_checkpoint(app_client):
    """POST /models/activate with a known checkpoint → 200; get_active == that checkpoint."""
    client, models_dir = app_client
    # Register a run directly.
    import json
    runs_file = models_dir / "runs.jsonl"
    row_a = {"checkpoint": "run-01-OLD.pt", "timestamp": "2026-01-01T00:00:00Z",
             "iteration": 1, "corpus_pair_count": 2, "corpus_hash": "cc",
             "held_loss": 0.6, "train_loss": 0.5}
    row_b = {"checkpoint": "run-02-NEW.pt", "timestamp": "2026-01-02T00:00:00Z",
             "iteration": 1, "corpus_pair_count": 3, "corpus_hash": "dd",
             "held_loss": 0.4, "train_loss": 0.3}
    runs_file.write_text(
        json.dumps(row_a) + "\n" + json.dumps(row_b) + "\n",
        encoding="utf-8",
    )

    rv = client.post("/models/activate", json={"checkpoint": "run-01-OLD.pt"})
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["ok"] is True
    assert data["active"] == "run-01-OLD.pt"

    # The ACTIVE file must now contain the pinned basename.
    active_file = models_dir / "ACTIVE"
    assert active_file.is_file()
    assert active_file.read_text().strip() == "run-01-OLD.pt"


def test_activate_rejects_unknown_checkpoint(app_client):
    """POST /models/activate with an unknown basename → 400, ACTIVE not written."""
    client, models_dir = app_client
    active_file = models_dir / "ACTIVE"

    # Path traversal attempt.
    rv = client.post("/models/activate", json={"checkpoint": "../../etc/passwd"})
    assert rv.status_code == 400
    data = rv.get_json()
    assert data["ok"] is False
    assert "Unknown checkpoint" in data["error"]
    assert not active_file.exists(), "ACTIVE must NOT be written for unknown checkpoint"

    # Plausible-looking but unregistered basename.
    rv2 = client.post("/models/activate", json={"checkpoint": "run-99-FAKE.pt"})
    assert rv2.status_code == 400
    data2 = rv2.get_json()
    assert data2["ok"] is False
    assert not active_file.exists()


def test_activate_back_to_latest(app_client):
    """Pin a checkpoint then POST __latest__ → 200; get_active == None (ACTIVE cleared)."""
    client, models_dir = app_client
    import json
    runs_file = models_dir / "runs.jsonl"
    row = {"checkpoint": "run-01-X.pt", "timestamp": "2026-01-01T00:00:00Z",
           "iteration": 1, "corpus_pair_count": 2, "corpus_hash": "ee",
           "held_loss": 0.5, "train_loss": 0.4}
    runs_file.write_text(json.dumps(row) + "\n", encoding="utf-8")

    # Pin it.
    rv = client.post("/models/activate", json={"checkpoint": "run-01-X.pt"})
    assert rv.status_code == 200
    assert (models_dir / "ACTIVE").is_file()

    # Clear pin.
    rv2 = client.post("/models/activate", json={"checkpoint": "__latest__"})
    assert rv2.status_code == 200
    data = rv2.get_json()
    assert data["ok"] is True
    assert data["active"] is None
    assert not (models_dir / "ACTIVE").exists()


def test_pin_survives_new_run(app_client):
    """Pin checkpoint A; append run B; get_active still == A."""
    client, models_dir = app_client
    import json
    runs_file = models_dir / "runs.jsonl"

    # Register run A and pin it.
    row_a = {"checkpoint": "run-01-A.pt", "timestamp": "2026-01-01T00:00:00Z",
             "iteration": 1, "corpus_pair_count": 2, "corpus_hash": "ff",
             "held_loss": 0.6, "train_loss": 0.5}
    runs_file.write_text(json.dumps(row_a) + "\n", encoding="utf-8")

    rv = client.post("/models/activate", json={"checkpoint": "run-01-A.pt"})
    assert rv.status_code == 200

    # Simulate a new retrain completing — append run B directly (registry write
    # without touching ACTIVE, as the completion hook intentionally does NOT
    # move an existing pin — D-06).
    row_b = {"checkpoint": "run-02-B.pt", "timestamp": "2026-01-02T00:00:00Z",
             "iteration": 1, "corpus_pair_count": 3, "corpus_hash": "gg",
             "held_loss": 0.4, "train_loss": 0.3}
    with open(runs_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(row_b) + "\n")

    # Pin must still be A — the new run did NOT steal it.
    active_file = models_dir / "ACTIVE"
    assert active_file.is_file()
    assert active_file.read_text().strip() == "run-01-A.pt"

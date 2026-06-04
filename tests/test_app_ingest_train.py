"""Tests for POST /ingest, POST /train, GET/POST /settings, and corpus upload UI.

Coverage:
  - test_ingest_valid_pair_renders_wav (@pytest.mark.slow — exercises real DawDreamer)
  - test_ingest_bad_manifest_no_dir     — bad JSON manifest → 400, no dir written
  - test_ingest_bad_midi_cleans_up      — valid manifest, empty MIDI → 400, partial dir removed
  - test_corpus_upload_ui_present       — GET /corpus contains upload UI ids
  - test_train_starts_and_status        — POST /train + GET /status (TrainingJob stubbed)
  - test_settings_roundtrip             — POST /settings, GET /settings echo
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pretty_midi
import pytest

from apollo.app.app import create_app


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_VALID_PATCH = {
    "spec_version": "1.0",
    "algorithm": 0,
    "gain": 0.8,
    "operators": [
        {"ratio": 1.0, "level": 0.5, "attack": 0.01, "decay": 0.1, "sustain": 0.7, "release": 0.1},
        {"ratio": 2.0, "level": 0.3, "attack": 0.01, "decay": 0.1, "sustain": 0.6, "release": 0.1},
        {"ratio": 3.0, "level": 0.2, "attack": 0.01, "decay": 0.1, "sustain": 0.5, "release": 0.1},
    ],
}


def _make_midi_bytes(pitch: int = 60, start: float = 0.0, end: float = 0.5) -> bytes:
    """Return bytes of a Type-0 MIDI file with a single note."""
    pm = pretty_midi.PrettyMIDI(initial_tempo=120.0)
    inst = pretty_midi.Instrument(program=0)
    inst.notes.append(pretty_midi.Note(velocity=80, pitch=pitch, start=start, end=end))
    pm.instruments.append(inst)
    buf = io.BytesIO()
    pm.write(buf)
    return buf.getvalue()


@pytest.fixture
def app_client(tmp_path):
    """Flask test client with an empty tmp pairs_root."""
    app = create_app(pairs_root=str(tmp_path))
    app.config["TESTING"] = True
    return app.test_client(), tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_ingest_valid_pair_renders_wav(app_client):
    """Happy path: valid call.mid + call_fm.json → 200, call.wav rendered.

    Decorated @slow because it exercises the real DawDreamer render path
    (~100–200ms).  Run with `pytest -k "not slow"` to skip in fast CI.
    """
    client, pairs_root = app_client
    mid_bytes = _make_midi_bytes(pitch=60, start=0.0, end=0.5)
    fm_bytes = json.dumps(_VALID_PATCH).encode()

    resp = client.post(
        "/ingest",
        data={
            "call_mid": (io.BytesIO(mid_bytes), "call.mid"),
            "call_fm": (io.BytesIO(fm_bytes), "call_fm.json"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data["ok"] is True
    nnn = data["nnn"]
    assert nnn == "000"

    pair_dir = pairs_root / nnn
    assert (pair_dir / "call.mid").is_file(), "call.mid missing"
    assert (pair_dir / "call_fm.json").is_file(), "call_fm.json missing"
    assert (pair_dir / "call.wav").is_file(), "call.wav not rendered"


def test_ingest_bad_manifest_no_dir(app_client):
    """Malformed call_fm.json → 400 + ok:False; no pair dir created."""
    client, pairs_root = app_client
    mid_bytes = _make_midi_bytes()

    resp = client.post(
        "/ingest",
        data={
            "call_mid": (io.BytesIO(mid_bytes), "call.mid"),
            "call_fm": (io.BytesIO(b"{not valid json"), "call_fm.json"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False

    # No pair dir should have been written.
    pair_dirs = [d for d in pairs_root.iterdir() if d.is_dir()]
    assert len(pair_dirs) == 0, f"Expected no pair dirs, found: {pair_dirs}"


def test_ingest_bad_midi_cleans_up(app_client):
    """Valid manifest + empty/invalid call.mid → 400; partially-allocated dir removed."""
    client, pairs_root = app_client
    fm_bytes = json.dumps(_VALID_PATCH).encode()

    resp = client.post(
        "/ingest",
        data={
            "call_mid": (io.BytesIO(b""), "call.mid"),   # empty — not a valid MIDI
            "call_fm": (io.BytesIO(fm_bytes), "call_fm.json"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False

    # Partially-allocated dir must have been cleaned up (Pitfall 5 guard).
    pair_dirs = [d for d in pairs_root.iterdir() if d.is_dir()]
    assert len(pair_dirs) == 0, f"Expected cleanup, found orphaned dirs: {pair_dirs}"


def test_corpus_upload_ui_present(app_client):
    """GET /corpus renders the upload UI with the required element ids."""
    client, _ = app_client
    resp = client.get("/corpus")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "call-mid-input" in body, "call-mid-input not in corpus.html"
    assert "call-fm-input" in body, "call-fm-input not in corpus.html"
    assert "add-pair-btn" in body, "add-pair-btn not in corpus.html"


def test_train_starts_and_status(app_client, monkeypatch):
    """POST /train + GET /status — TrainingJob.start is stubbed (no real subprocess)."""
    client, _ = app_client

    # Stub TrainingJob.start to avoid spawning a real process.
    from apollo.app import jobs

    start_called = []

    def fake_start(self, pairs_root, epochs, output_dir):
        start_called.append((pairs_root, epochs, output_dir))
        with self._lock:
            self.status = "running"
            self.epoch = 0
            self.total_epochs = epochs
        return True

    monkeypatch.setattr(jobs.TrainingJob, "start", fake_start)

    resp = client.post("/train")
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["ok"] is True
    assert len(start_called) == 1, "start should have been called once"

    # GET /status should reflect the stubbed state.
    status_resp = client.get("/status")
    assert status_resp.status_code == 200
    s = status_resp.get_json()
    assert s["status"] == "running"


def test_settings_roundtrip(app_client):
    """POST /settings persists changes; GET /settings echoes them back."""
    client, _ = app_client

    resp = client.post(
        "/settings",
        data=json.dumps({"responses_dir": "/tmp/myresp", "auto_retrain": True}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    # Path is resolved, so ends with /myresp
    assert data["responses_dir"].endswith("myresp")
    assert data["auto_retrain"] is True

    # GET should echo the same values.
    get_resp = client.get("/settings")
    assert get_resp.status_code == 200
    get_data = get_resp.get_json()
    assert get_data["ok"] is True
    assert get_data["responses_dir"].endswith("myresp")
    assert get_data["auto_retrain"] is True

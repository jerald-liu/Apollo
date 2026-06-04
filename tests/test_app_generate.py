"""Tests for /presets, POST /generate, and GET /responses routes (Plan 05-04).

Coverage:
  - test_presets_listed_and_valid           — GET /presets lists 3 names; GET /presets/bright_bell → 200 JSON
  - test_preset_traversal_rejected          — traversal-ish name → 400/404
  - test_generate_no_checkpoint             — no .pt under models/ → 400 with no-checkpoint copy; no orphan dir
  - test_generate_happy_path_stubbed        — monkeypatched subprocess + checkpoint → 200; response copied to RESPONSES_DIR
  - test_responses_endpoint                 — after stubbed generate, GET /responses lists the copied file
"""
from __future__ import annotations

import io
import json
import shutil
import subprocess
from pathlib import Path

import pretty_midi
import pytest

from apollo.app.app import create_app


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_VALID_PATCH = {
    "spec_version": "1.1",
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
    """Flask test client with a tmp pairs_root and tmp responses_dir."""
    responses_dir = tmp_path / "responses"
    app = create_app(pairs_root=str(tmp_path / "pairs"))
    app.config["TESTING"] = True
    app.config["RESPONSES_DIR"] = responses_dir
    return app.test_client(), tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_presets_listed_and_valid(app_client):
    """GET /presets includes the 3 bundled names; GET /presets/bright_bell returns valid JSON."""
    client, _ = app_client

    resp = client.get("/presets")
    assert resp.status_code == 200
    names = resp.get_json()
    assert isinstance(names, list)
    assert "bright_bell" in names
    assert "warm_pad" in names
    assert "vibrato_lead" in names

    # Fetch one preset — should be valid JSON with expected fields.
    resp2 = client.get("/presets/bright_bell")
    assert resp2.status_code == 200
    preset = json.loads(resp2.data)
    assert "algorithm" in preset
    assert "operators" in preset
    assert preset["spec_version"] in ("1.0", "1.1")


def test_preset_traversal_rejected(app_client):
    """GET /presets with a traversal-ish name → 400 or 404 (T-05-12)."""
    client, _ = app_client

    # Dot in name (traversal attempt)
    assert client.get("/presets/..").status_code in (400, 404)

    # URL-encoded slash (Flask decodes %2F as path separator, still should be safe)
    assert client.get("/presets/..%2fetc%2fpasswd").status_code in (400, 404)

    # Uppercase letters (not in [a-z_]) → 400
    assert client.get("/presets/BrightBell").status_code in (400, 404)

    # Digits → 400
    assert client.get("/presets/123").status_code in (400, 404)


def test_generate_no_checkpoint(app_client, monkeypatch, tmp_path):
    """POST /generate with no .pt → 400 with no-checkpoint copy; no orphan pair dir."""
    client, root = app_client

    # Point the app at an empty models dir (no .pt).
    import apollo.app.app as app_module
    monkeypatch.setattr(app_module, "_RESPONSE_FILENAME_RE", app_module._RESPONSE_FILENAME_RE)

    # Monkey-patch _latest_checkpoint to return None (no model).
    # We do this by patching the function in the closure via the app's internal.
    # Because _latest_checkpoint is defined inside create_app closure, we monkey-patch
    # at the module level by patching the Path("models").glob call result:
    # Simpler: just ensure models/ dir doesn't exist (create_app uses cwd).
    # The fixture's tmp_path has no models/ dir, but the test runs in the project cwd.
    # We need to intercept _latest_checkpoint. Since it's a closure, patch subprocess and
    # also monkeypatch the Path("models") check by ensuring no models/*.pt exists.
    # Best approach: monkeypatch Path.glob to return empty iterator for models/*.pt.

    # Actually, the easiest way: create the app fresh with a monkeypatched _latest_checkpoint.
    # We'll use monkeypatch on the module's subprocess import to intercept at that level.
    # Since _latest_checkpoint is an inner closure, let's test it via a fresh app instance
    # where we ensure the cwd has no models/*.pt.
    # Create a temporary directory to use as cwd during the test.
    test_cwd = tmp_path / "test_cwd_no_ckpt"
    test_cwd.mkdir()
    (test_cwd / "pairs").mkdir()
    responses_dir = test_cwd / "responses"

    import os
    old_cwd = os.getcwd()
    os.chdir(str(test_cwd))
    try:
        fresh_app = create_app(pairs_root=str(test_cwd / "pairs"))
        fresh_app.config["TESTING"] = True
        fresh_app.config["RESPONSES_DIR"] = responses_dir
        c = fresh_app.test_client()

        mid_bytes = _make_midi_bytes()
        fm_bytes = json.dumps(_VALID_PATCH).encode()

        resp = c.post(
            "/generate",
            data={
                "call_mid": (io.BytesIO(mid_bytes), "call.mid"),
                "call_fm": (io.BytesIO(fm_bytes), "call_fm.json"),
            },
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.get_json()}"
        data = resp.get_json()
        assert data["ok"] is False
        # UI-SPEC no-checkpoint copy must be in the error message.
        assert "No trained model yet" in data["error"], f"Unexpected error: {data['error']}"

        # No orphan pair dir should remain.
        pairs_dir = test_cwd / "pairs"
        orphans = [d for d in pairs_dir.iterdir() if d.is_dir()] if pairs_dir.exists() else []
        assert len(orphans) == 0, f"Orphan dirs remain: {orphans}"
    finally:
        os.chdir(old_cwd)


def test_generate_happy_path_stubbed(app_client, monkeypatch, tmp_path):
    """POST /generate with stubbed subprocess + checkpoint → 200; response copied to RESPONSES_DIR.

    Stubs subprocess.run (in apollo.app.app) to write response_001.mid into the pair
    dir and return returncode 0 — avoids loading a real checkpoint or running inference.
    Also stubs _latest_checkpoint (via monkeypatching Path) to return a dummy path.
    """
    client, root = app_client
    responses_dir: Path = root / "responses"

    # We need models/dummy.pt to exist so _latest_checkpoint finds it.
    # Create it under cwd since _latest_checkpoint uses Path("models").
    import os
    test_cwd = tmp_path / "test_cwd_happy"
    test_cwd.mkdir()
    pairs_dir = test_cwd / "pairs"
    pairs_dir.mkdir()
    models_dir = test_cwd / "models"
    models_dir.mkdir()
    dummy_ckpt = models_dir / "dummy.pt"
    dummy_ckpt.write_bytes(b"fake checkpoint")

    fresh_app = create_app(pairs_root=str(pairs_dir))
    fresh_app.config["TESTING"] = True
    fresh_app.config["RESPONSES_DIR"] = responses_dir

    # Stub subprocess.run in apollo.app.app to simulate generate.py writing response_001.mid.
    import apollo.app.app as app_module

    def fake_subprocess_run(argv, capture_output, text):
        """Simulate generate.py: find the pair dir from argv, write response_001.mid."""
        # argv = ["python", "-m", "apollo.scripts.generate", <ckpt>, <call.mid>]
        call_mid_path = Path(argv[-1])
        pair_dir = call_mid_path.parent
        response_path = pair_dir / "response_001.mid"
        # Write a minimal MIDI file as the response.
        pm = pretty_midi.PrettyMIDI(initial_tempo=120.0)
        inst = pretty_midi.Instrument(program=0)
        inst.notes.append(pretty_midi.Note(velocity=80, pitch=64, start=0.0, end=0.4))
        pm.instruments.append(inst)
        pm.write(str(response_path))

        class FakeResult:
            returncode = 0
            stderr = ""

        return FakeResult()

    monkeypatch.setattr(app_module.subprocess, "run", fake_subprocess_run)

    old_cwd = os.getcwd()
    os.chdir(str(test_cwd))
    try:
        c = fresh_app.test_client()
        mid_bytes = _make_midi_bytes()
        fm_bytes = json.dumps(_VALID_PATCH).encode()

        resp = c.post(
            "/generate",
            data={
                "call_mid": (io.BytesIO(mid_bytes), "call.mid"),
                "call_fm": (io.BytesIO(fm_bytes), "call_fm.json"),
            },
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.get_json()}"
        data = resp.get_json()
        assert data["ok"] is True
        assert "nnn" in data
        assert "response" in data

        # A response file must have been copied into RESPONSES_DIR.
        assert responses_dir.is_dir(), "RESPONSES_DIR not created"
        copied = list(responses_dir.iterdir())
        assert len(copied) >= 1, f"No file copied to RESPONSES_DIR: {list(responses_dir.iterdir())}"
        # The copied file must be a .mid file.
        assert any(f.suffix == ".mid" for f in copied), f"No .mid in RESPONSES_DIR: {copied}"
    finally:
        os.chdir(old_cwd)


def test_responses_endpoint(app_client, monkeypatch, tmp_path):
    """GET /responses lists copied response files after a stubbed generate."""
    import os
    import apollo.app.app as app_module

    test_cwd = tmp_path / "test_cwd_responses"
    test_cwd.mkdir()
    pairs_dir = test_cwd / "pairs"
    pairs_dir.mkdir()
    models_dir = test_cwd / "models"
    models_dir.mkdir()
    (models_dir / "dummy.pt").write_bytes(b"fake")
    responses_dir = test_cwd / "responses"

    fresh_app = create_app(pairs_root=str(pairs_dir))
    fresh_app.config["TESTING"] = True
    fresh_app.config["RESPONSES_DIR"] = responses_dir

    def fake_subprocess_run(argv, capture_output, text):
        call_mid_path = Path(argv[-1])
        pair_dir = call_mid_path.parent
        response_path = pair_dir / "response_001.mid"
        pm = pretty_midi.PrettyMIDI(initial_tempo=120.0)
        inst = pretty_midi.Instrument(program=0)
        inst.notes.append(pretty_midi.Note(velocity=80, pitch=64, start=0.0, end=0.4))
        pm.instruments.append(inst)
        pm.write(str(response_path))

        class FakeResult:
            returncode = 0
            stderr = ""

        return FakeResult()

    monkeypatch.setattr(app_module.subprocess, "run", fake_subprocess_run)

    old_cwd = os.getcwd()
    os.chdir(str(test_cwd))
    try:
        c = fresh_app.test_client()

        # Before generate: /responses should return empty list.
        resp = c.get("/responses")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["responses"] == []

        # Do a generate.
        mid_bytes = _make_midi_bytes()
        fm_bytes = json.dumps(_VALID_PATCH).encode()
        gen_resp = c.post(
            "/generate",
            data={
                "call_mid": (io.BytesIO(mid_bytes), "call.mid"),
                "call_fm": (io.BytesIO(fm_bytes), "call_fm.json"),
            },
            content_type="multipart/form-data",
        )
        assert gen_resp.status_code == 200

        # After generate: /responses should list the copied file.
        resp2 = c.get("/responses")
        assert resp2.status_code == 200
        data2 = resp2.get_json()
        assert data2["ok"] is True
        assert len(data2["responses"]) >= 1
        assert any(".mid" in name for name in data2["responses"])
    finally:
        os.chdir(old_cwd)

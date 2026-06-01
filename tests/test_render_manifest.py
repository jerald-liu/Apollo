"""Tests for write_render_manifest (EVAL-03, EVAL-05; D-11..D-13).

Manifest schema is the M4L device's protocol — these tests pin it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from apollo.eval.render_manifest import write_render_manifest
from apollo.eval.heldout import enumerate_heldout
from apollo.ingest import synthesize_pair


@pytest.fixture
def pairs_root(tmp_path) -> Path:
    # Synthesize 10 mock pairs; ~2 will hash to held-out (k=5).
    for i in range(10):
        synthesize_pair(tmp_path, nnn=f"{i:03d}")
    return tmp_path


def _touch_response(pairs_root: Path, nnn: str) -> Path:
    rm = pairs_root / nnn / "response_001.mid"
    rm.write_bytes(b"MThd\x00\x00\x00\x06")  # not a real MIDI; bytes are not parsed here
    return rm


def test_manifest_contains_only_heldout(pairs_root, tmp_path):
    heldout_nnns = {p.nnn for p in enumerate_heldout(str(pairs_root))}
    for nnn in heldout_nnns:
        _touch_response(pairs_root, nnn)
    manifest_path = tmp_path / "active.json"
    out = write_render_manifest("rid_test", str(pairs_root), str(manifest_path))
    assert out == manifest_path
    data = json.loads(manifest_path.read_text())
    assert data["run_id"] == "rid_test"
    seen = {e["nnn"] for e in data["entries"]}
    assert seen == heldout_nnns


def test_manifest_skips_pairs_missing_response(pairs_root, tmp_path, capsys):
    heldout = list(enumerate_heldout(str(pairs_root)))
    assert len(heldout) >= 1, "fixture must produce at least one held-out pair"
    # Touch response for the first held-out pair only.
    _touch_response(pairs_root, heldout[0].nnn)
    manifest_path = tmp_path / "active.json"
    write_render_manifest("rid_test", str(pairs_root), str(manifest_path))
    data = json.loads(manifest_path.read_text())
    seen = {e["nnn"] for e in data["entries"]}
    assert seen == {heldout[0].nnn}
    # Other held-out pairs produced a warning on stderr.
    if len(heldout) > 1:
        captured = capsys.readouterr()
        assert "no response_001.mid" in captured.err


def test_manifest_entry_schema(pairs_root, tmp_path):
    heldout = list(enumerate_heldout(str(pairs_root)))
    if not heldout:
        pytest.skip("fixture produced no held-out pairs (hash-determined)")
    _touch_response(pairs_root, heldout[0].nnn)
    manifest_path = tmp_path / "active.json"
    write_render_manifest("rid_abc", str(pairs_root), str(manifest_path))
    entry = json.loads(manifest_path.read_text())["entries"][0]
    assert set(entry.keys()) == {"nnn", "response_mid", "out_wav", "notes_json"}
    assert entry["out_wav"].endswith(f"eval/rid_abc/response.wav")
    assert entry["notes_json"].endswith("response_001.notes.json")


def test_manifest_parent_dir_created(pairs_root, tmp_path):
    manifest_path = tmp_path / "deep" / "nested" / "active.json"
    write_render_manifest("rid", str(pairs_root), str(manifest_path))
    assert manifest_path.is_file()


def test_apollo_eval_reexports():
    import apollo.eval as e
    for sym in ("enumerate_heldout", "compute_run_id", "append_run",
                "append_score", "append_score_pair", "load_scores",
                "check_ship_gate", "write_render_manifest"):
        assert hasattr(e, sym), f"missing re-export: {sym}"

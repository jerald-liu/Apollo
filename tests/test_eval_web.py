"""Smoke tests for the Phase-4 Flask grading UI (EVAL-02).

Uses Flask's test_client — no actual port binding.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from apollo.eval.web.app import create_app
from apollo.eval.heldout import enumerate_heldout
from apollo.ingest import synthesize_pair


@pytest.fixture
def pairs_root(tmp_path) -> Path:
    for i in range(10):
        synthesize_pair(tmp_path, nnn=f"{i:03d}")
    return tmp_path


@pytest.fixture
def app(pairs_root, tmp_path):
    scores_path = str(tmp_path / "scores.jsonl")
    runs_path = str(tmp_path / "runs.jsonl")
    # Seed one runs.jsonl row so /reveal has something to read.
    Path(runs_path).write_text(json.dumps({
        "run_id": "testrun00000000",
        "checkpoint_path": "models/fake.pt",
        "iteration": True,
    }) + "\n")
    return create_app(
        pairs_root=str(pairs_root),
        run_id="testrun00000000",
        runs_path=runs_path,
        scores_path=scores_path,
    )


def test_index_returns_worklist(app, pairs_root):
    with app.test_client() as c:
        r = c.get("/")
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        assert "Apollo" in body
        # At least one held-out pair nnn is present in the worklist body.
        heldout = {p.nnn for p in enumerate_heldout(str(pairs_root))}
        assert any(nnn in body for nnn in heldout)


def test_pair_view_valid_nnn(app, pairs_root):
    heldout = list(enumerate_heldout(str(pairs_root)))
    assert heldout, "fixture must produce at least one held-out pair"
    with app.test_client() as c:
        r = c.get(f"/pair/{heldout[0].nnn}")
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        assert "Call-Response Fit" in body
        assert "Musical Coherence" in body


def test_pair_view_unknown_nnn_returns_404(app):
    with app.test_client() as c:
        r = c.get("/pair/999")
        assert r.status_code == 404


def test_pair_view_path_traversal_returns_404(app):
    with app.test_client() as c:
        r = c.get("/pair/..%2F..%2Fetc%2Fpasswd")
        assert r.status_code == 404


def test_audio_call_wav_valid(app, pairs_root):
    heldout = list(enumerate_heldout(str(pairs_root)))
    with app.test_client() as c:
        r = c.get(f"/audio/{heldout[0].nnn}/call.wav")
        assert r.status_code == 200
        assert r.mimetype == "audio/wav"


def test_audio_response_wav_missing_returns_404(app, pairs_root):
    # synthesize_pair does NOT create eval/<run>/response.wav
    heldout = list(enumerate_heldout(str(pairs_root)))
    with app.test_client() as c:
        r = c.get(f"/audio/{heldout[0].nnn}/response.wav")
        assert r.status_code == 404


def test_audio_path_traversal_blocked(app):
    with app.test_client() as c:
        r = c.get("/audio/..%2F..%2Fetc%2Fpasswd/call.wav")
        assert r.status_code == 404


def test_post_score_appends_two_lines(app, pairs_root, tmp_path):
    heldout = list(enumerate_heldout(str(pairs_root)))
    nnn = heldout[0].nnn
    with app.test_client() as c:
        r = c.post("/score", json={
            "pair_id": nnn, "fit": 4, "coherence": 3, "note": "test"
        })
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is True
    scores_path = app.config["SCORES_PATH"]
    lines = Path(scores_path).read_text().splitlines()
    assert len(lines) == 2
    recs = [json.loads(l) for l in lines]
    assert {r["dim"] for r in recs} == {"fit", "coherence"}


def test_post_score_unknown_pair_returns_404(app):
    with app.test_client() as c:
        r = c.post("/score", json={
            "pair_id": "999", "fit": 4, "coherence": 3, "note": ""
        })
        assert r.status_code == 404


def test_post_score_out_of_range_returns_400(app, pairs_root):
    heldout = list(enumerate_heldout(str(pairs_root)))
    with app.test_client() as c:
        r = c.post("/score", json={
            "pair_id": heldout[0].nnn, "fit": 7, "coherence": 3
        })
        assert r.status_code == 400


def test_reveal_returns_run_metadata(app, pairs_root):
    heldout = list(enumerate_heldout(str(pairs_root)))
    with app.test_client() as c:
        r = c.get(f"/reveal/{heldout[0].nnn}")
        assert r.status_code == 200
        data = r.get_json()
        assert data["run_id"] == "testrun00000000"
        assert data["checkpoint_path"] == "models/fake.pt"
        assert data["iteration"] is True


def test_score_get_prepopulates_after_submit(app, pairs_root):
    heldout = list(enumerate_heldout(str(pairs_root)))
    nnn = heldout[0].nnn
    with app.test_client() as c:
        c.post("/score", json={"pair_id": nnn, "fit": 4, "coherence": 3, "note": "x"})
        r = c.get(f"/score/{nnn}")
        data = r.get_json()
        assert data["fit"] == 4
        assert data["coherence"] == 3
        assert data["note"] == "x"


def test_score_get_returns_nulls_for_ungraded(app, pairs_root):
    heldout = list(enumerate_heldout(str(pairs_root)))
    with app.test_client() as c:
        r = c.get(f"/score/{heldout[0].nnn}")
        data = r.get_json()
        assert data["fit"] is None
        assert data["coherence"] is None

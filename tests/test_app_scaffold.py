"""Smoke tests for the Phase-5 Flask app scaffold (APP-01, APP-02).

Uses Flask's test_client — no actual port binding.

Verifies:
- Dashboard renders with trust badge (APP-02)
- /status returns idle snapshot before any training (APP-01)
- _known_pairs_set enumerates pairs by call.mid + call_fm.json presence,
  NOT call.wav presence (RESEARCH Pitfall 5)
- Path-traversal rejection: unknown or traversal nnn → 404 (T-05-01)
- Audio filename allow-list: non-call.wav filename → 400 (T-05-01)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from apollo.app.app import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def pairs_root(tmp_path) -> Path:
    """Create a pairs directory with one valid pair (007/).

    The pair has call.mid (empty — load_notes is not called here) and a
    minimal valid call_fm.json. call.wav is intentionally absent to verify
    that _known_pairs_set does not require it (RESEARCH Pitfall 5).
    """
    pair_dir = tmp_path / "007"
    pair_dir.mkdir()

    # Empty call.mid — sufficient for _known_pairs_set (it only checks presence)
    (pair_dir / "call.mid").write_bytes(b"")

    # Minimal valid call_fm.json (3 operators, algorithm 0, spec_version 1.0)
    call_fm = {
        "spec_version": "1.0",
        "algorithm": 0,
        "operators": [
            {"ratio": 1.0, "level": 0.5, "attack": 0.01, "decay": 0.1,
             "sustain": 0.7, "release": 0.1},
            {"ratio": 1.0, "level": 0.5, "attack": 0.01, "decay": 0.1,
             "sustain": 0.7, "release": 0.1},
            {"ratio": 1.0, "level": 0.5, "attack": 0.01, "decay": 0.1,
             "sustain": 0.7, "release": 0.1},
        ],
        "gain": 0.8,
    }
    (pair_dir / "call_fm.json").write_text(json.dumps(call_fm), encoding="utf-8")

    return tmp_path


@pytest.fixture
def app(pairs_root):
    return create_app(pairs_root=str(pairs_root))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_dashboard_renders(app):
    """GET / returns 200 and contains the trust badge (APP-02)."""
    with app.test_client() as c:
        r = c.get("/")
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        assert "trust-badge" in body


def test_status_idle(app):
    """GET /status returns JSON with status=='idle' and epoch==0 before training."""
    with app.test_client() as c:
        r = c.get("/status")
        assert r.status_code == 200
        data = r.get_json()
        assert data["status"] == "idle"
        assert data["epoch"] == 0


def test_known_pair_enumerated(app, pairs_root):
    """Dashboard n_pairs == 1: pair with call.mid + call_fm.json is counted.

    call.wav is intentionally absent from the fixture — _known_pairs_set must
    enumerate the pair regardless (RESEARCH Pitfall 5: discover_pairs requires
    call.wav; _known_pairs_set only requires call.mid + call_fm.json).
    """
    assert not (pairs_root / "007" / "call.wav").exists(), \
        "Fixture must NOT have call.wav — this tests Pitfall 5 mitigation"
    with app.test_client() as c:
        r = c.get("/")
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        # The template renders n_pairs; check that "1" appears somewhere
        # meaningful (e.g. "1 of 30 pairs — keep going")
        assert "1 of 30" in body or ">1<" in body


def test_unknown_nnn_404(app):
    """Unknown or traversal nnn → 404 from _validate_pair_nnn (T-05-01)."""
    with app.test_client() as c:
        # Unknown nnn
        r = c.get("/midi/999/call.mid")
        assert r.status_code == 404

        # Path traversal attempt — nnn is not in known pairs set
        r = c.get("/midi/../etc/call.mid")
        assert r.status_code == 404


def test_audio_bad_filename_400(app):
    """GET /audio/<known_nnn>/<non-call.wav> → 400 (filename allow-list, T-05-01)."""
    with app.test_client() as c:
        r = c.get("/audio/007/secrets.txt")
        assert r.status_code == 400

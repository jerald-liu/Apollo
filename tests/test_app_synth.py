"""Tests for the Phase-5 browser FM synth (APP-05) and /corpus + /midi routes (APP-10, APP-11).

Two test groups:
  (1) synth.js static structure — read file as text; no JS runtime needed.
  (2) Flask /corpus + /midi behavior — uses tmp_path pairs_root fixture.
"""
from __future__ import annotations

import json
from pathlib import Path

import pretty_midi
import pytest

from apollo.app.app import create_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_midi_one_note(path: Path, pitch: int = 60, start: float = 0.0, end: float = 0.5):
    """Write a Type-0 MIDI file with a single note to *path*."""
    pm = pretty_midi.PrettyMIDI(initial_tempo=120.0)
    inst = pretty_midi.Instrument(program=0)
    inst.notes.append(pretty_midi.Note(velocity=80, pitch=pitch, start=start, end=end))
    pm.instruments.append(inst)
    pm.write(str(path))


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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def pairs_root(tmp_path) -> Path:
    """Pairs directory with pair 005 (valid) and pair 006 (invalid call_fm.json)."""
    # Pair 005 — valid
    pair_005 = tmp_path / "005"
    pair_005.mkdir()
    _write_midi_one_note(pair_005 / "call.mid", pitch=60, start=0.0, end=0.5)
    (pair_005 / "call_fm.json").write_text(json.dumps(_VALID_PATCH), encoding="utf-8")

    # Pair 006 — invalid JSON
    pair_006 = tmp_path / "006"
    pair_006.mkdir()
    (pair_006 / "call.mid").write_bytes(b"")
    (pair_006 / "call_fm.json").write_text("{not valid json}", encoding="utf-8")

    return tmp_path


@pytest.fixture
def app(pairs_root):
    return create_app(pairs_root=str(pairs_root))


# ---------------------------------------------------------------------------
# Group 1: synth.js static structure checks
# ---------------------------------------------------------------------------

SYNTH_JS_PATH = Path(__file__).parent.parent / "apollo" / "app" / "static" / "synth.js"


def _synth_source() -> str:
    return SYNTH_JS_PATH.read_text(encoding="utf-8")


def test_synth_js_exists():
    """synth.js must exist."""
    assert SYNTH_JS_PATH.is_file(), "apollo/app/static/synth.js not found"


def test_synth_js_min_lines():
    """synth.js must be at least 80 lines."""
    lines = _synth_source().splitlines()
    assert len(lines) >= 80, f"synth.js only {len(lines)} lines — expected ≥80"


def test_synth_js_functions_present():
    """Core functions must all be declared in synth.js."""
    src = _synth_source()
    for name in ("function playNote", "applyAdsr", "attachLfo", "playSequence"):
        assert name in src, f"synth.js missing: {name}"


def test_synth_js_algorithm_branches():
    """synth.js must handle all three algorithm numeric values (0, 1, 2)."""
    src = _synth_source()
    # ALGORITHMS constant or numeric literals for STACK/PARALLEL_MODS/CARRIER_PAIR
    # The file references ALGORITHMS.STACK etc. or branches on 0/1/2.
    assert "ALGORITHMS" in src or (
        "alg === 0" in src or "=== 0" in src
    ), "synth.js missing algorithm branching"


def test_synth_js_mod_level_freq_scaling():
    """Modulator amplitude must scale by op_level*freq (DX-style index)."""
    src = _synth_source()
    # Accept 'level * freq' or 'level*freq' variations
    import re
    assert re.search(r"level\s*\*\s*freq", src), "synth.js missing op_level*freq mod scaling"


def test_synth_js_tremolo_formula():
    """Tremolo formula must reference '1 - depth' (from CORPUS-CONVENTIONS.md)."""
    src = _synth_source()
    assert "1 - depth" in src, "synth.js missing tremolo formula '1 - depth'"


def test_synth_js_vibrato_cents():
    """Vibrato approx must use 1200 (cents denominator)."""
    src = _synth_source()
    assert "1200" in src, "synth.js missing vibrato '1200' cents denominator"


def test_synth_js_lfo_wave_array():
    """LFO wave type array must map [sine, triangle, square]."""
    src = _synth_source()
    assert "'sine','triangle','square'" in src or "'sine', 'triangle', 'square'" in src, \
        "synth.js missing LFO wave type array"


def test_synth_js_no_tone_js():
    """synth.js must NOT reference Tone.js (it is 2-op only; forbidden by RESEARCH)."""
    src = _synth_source()
    import re
    assert not re.search(r"Tone\.", src), "synth.js must not reference Tone.js"


def test_synth_js_lfo_per_note_osc():
    """attachLfo must create a new OscillatorNode (per-note phase reset)."""
    src = _synth_source()
    assert "createOscillator" in src, "synth.js missing createOscillator in attachLfo"


# ---------------------------------------------------------------------------
# Group 2: Flask /corpus + /midi behavior
# ---------------------------------------------------------------------------

def test_corpus_lists_pair(app):
    """GET /corpus → 200; body contains 'play-call' and 'patch-005' for valid pair."""
    with app.test_client() as c:
        r = c.get("/corpus")
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        assert "play-call" in body, "corpus page missing 'play-call' button"
        assert "patch-005" in body, "corpus page missing 'patch-005' script tag"


def test_midi_notes_json(app):
    """GET /midi/005/call.mid → 200; JSON list with pitch==60."""
    with app.test_client() as c:
        r = c.get("/midi/005/call.mid")
        assert r.status_code == 200
        notes = r.get_json()
        assert isinstance(notes, list), f"Expected list, got {type(notes)}"
        assert len(notes) >= 1, "Expected at least one note"
        note = notes[0]
        for key in ("pitch", "velocity", "start", "duration"):
            assert key in note, f"Note missing key: {key}"
        assert note["pitch"] == 60, f"Expected pitch 60, got {note['pitch']}"


def test_corpus_invalid_manifest_marked(app):
    """GET /corpus → 200; pair 006 shows 'invalid call_fm.json', no patch-006 script tag."""
    with app.test_client() as c:
        r = c.get("/corpus")
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        assert "invalid call_fm.json" in body, \
            "corpus page must display 'invalid call_fm.json' for pair 006"
        assert "patch-006" not in body, \
            "corpus page must NOT emit 'patch-006' script tag for invalid pair"

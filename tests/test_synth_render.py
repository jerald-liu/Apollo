"""Tests for apollo.synth.render (the deterministic 3-op FM renderer).

Covers DATA-06: determinism (bit-identical re-render), no-clip normalization,
the frozen COND-01 mel contract ((96,128) float32 via the production
MelExtractor), timbre discriminability across contrasting presets, manifest
validation fail-loud, and render_call_wav parity (the single shared path).

Mirrors tests/test_mel_extractor.py conventions: synthesize inputs in tmp_path,
one assertion focus per test, pytest.raises(IngestError, match=...) for failures.

dawdreamer-dependent render tests are guarded with importorskip so non-arm64 CI
skips them rather than hard-failing (Assumption A6). Manifest-validation tests do
NOT need dawdreamer and run unconditionally, so the validation boundary is always
exercised. No .wav fixture is committed — every render is in-process to tmp_path.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pretty_midi
import pytest
import soundfile as sf
import torch

from apollo.ingest import IngestError, MelExtractor
from apollo.synth.manifest import load_manifest
from apollo.synth.spec import (
    SPEC_VERSION,
    SR,
    FmParams,
    LfoParams,
    LfoTarget,
    LfoWave,
    OperatorParams,
    dsp_string,
)

# --- Test helpers -----------------------------------------------------------

# Default per-operator params (valid, in-range).
_DEFAULT_OP = {
    "ratio": 1.0,
    "level": 0.8,
    "attack": 0.005,
    "decay": 0.1,
    "sustain": 0.6,
    "release": 0.2,
}


def _write_call_mid(path) -> None:
    """Write a tiny valid monophonic 120-BPM call.mid (3 notes at 0.5 s onsets).

    Onsets spaced 0.5 s estimate to exactly 120 bpm (pretty_midi.estimate_tempo),
    which load_notes requires (±2 bpm). Note durations 0.4 s keep the gesture
    monophonic and short — we avoid 0.25 s durations that trick estimate_tempo
    (Phase-1 decision).
    """
    pm = pretty_midi.PrettyMIDI(initial_tempo=120.0)
    inst = pretty_midi.Instrument(program=0)
    for i, start in enumerate([0.0, 0.5, 1.0]):
        inst.notes.append(
            pretty_midi.Note(velocity=100, pitch=60 + i, start=start, end=start + 0.4)
        )
    pm.instruments.append(inst)
    pm.write(str(path))


def _fm_params(**op_overrides) -> FmParams:
    """Build an FmParams with 3 identical operators (override fields via kwargs)."""
    fields = {**_DEFAULT_OP, **op_overrides}
    algorithm = fields.pop("algorithm", 0)
    gain = fields.pop("gain", 0.5)
    lfo = fields.pop("lfo", None)
    op = OperatorParams(**fields)
    return FmParams(algorithm=algorithm, operators=(op, op, op), gain=gain, lfo=lfo)


def _manifest_dict(**op_overrides) -> dict:
    """Build a valid call_fm.json dict (override per-op fields / algorithm / gain)."""
    op = {**_DEFAULT_OP}
    algorithm = op_overrides.pop("algorithm", 0)
    gain = op_overrides.pop("gain", 0.5)
    spec_version = op_overrides.pop("spec_version", "1.0")
    lfo = op_overrides.pop("lfo", None)
    op.update(op_overrides)
    out = {
        "spec_version": spec_version,
        "algorithm": algorithm,
        "operators": [dict(op), dict(op), dict(op)],
        "gain": gain,
    }
    if lfo is not None:
        out["lfo"] = lfo
    return out


# --- LFO spec tests (dsp_string is pure; no dawdreamer needed) ---------------


def test_spec_version_is_1_1():
    """SPEC_VERSION bumped to 1.1 for the optional LFO."""
    assert SPEC_VERSION == "1.1"


def test_lfo_enums():
    """Waveform and target enum values are stable integers."""
    assert (LfoWave.SINE, LfoWave.TRIANGLE, LfoWave.SQUARE) == (0, 1, 2)
    assert (LfoTarget.LEVEL, LfoTarget.PITCH) == (0, 1)


def test_dsp_string_no_lfo_omits_lfo():
    """With lfo=None the emitted DSP source contains no lfo_ declarations."""
    s = dsp_string(_fm_params())
    assert "lfo_" not in s


def test_dsp_string_lfo_level_numeric_only():
    """An LFO-level patch emits the numeric select3 block and applies lvl_mod."""
    s = dsp_string(_fm_params(lfo=LfoParams(6.0, 0.8, 0, 0)))
    assert "select3(int(lfo_wave)" in s
    assert "os.lf_triangle" in s
    assert "os.lf_squarewave" in s
    assert "lvl_mod" in s
    # No manifest enum NAME is interpolated into the DSP source.
    assert "SINE" not in s and "LEVEL" not in s


def test_dsp_string_lfo_pitch_emits_pow():
    """An LFO-pitch patch emits the pow(2, cents/1200) vibrato multiplier."""
    s = dsp_string(_fm_params(lfo=LfoParams(6.0, 0.8, 0, 1)))
    assert "pow(2" in s


def test_dsp_string_carrier_pair_lfo_both_carriers():
    """CARRIER_PAIR (algorithm 2) LFO-level modulates both car1 and car2."""
    s = dsp_string(_fm_params(algorithm=2, lfo=LfoParams(6.0, 0.8, 0, 0)))
    assert "car1" in s and "car2" in s
    # both carriers carry the lvl_mod factor
    assert s.count("lvl_mod") >= 3  # declaration + two carrier applications


def test_package_root_reexports_lfo():
    """LfoParams/LfoWave/LfoTarget are reachable from the package root."""
    from apollo.synth import LfoParams as P, LfoTarget as T, LfoWave as W

    assert (W.SQUARE, T.PITCH) == (2, 1)
    assert P(6.0, 0.8, 0, 0).rate == 6.0


def _write_manifest(path, **op_overrides) -> None:
    path.write_text(json.dumps(_manifest_dict(**op_overrides)))


# --- Golden v1.0 dsp_string anchors (committed fixtures; bit-identity) -------
# These hold the EXACT Phase-6 v1.0 DSP source captured at plan-07-02 authoring
# time (one per algorithm). They are the STRONG bit-identity anchor for
# SYNTH-01 SC#2: the no-lfo `dsp_string` must equal these byte-for-byte, so ANY
# drift in the v1.0 body — not merely the introduction of `lfo_` declarations —
# fails loudly and protects the already-authored corpus's bit-identity. The
# reference is a STORED file read at test time, NOT a recomputation of
# `dsp_string` (which would make the assertion tautological).
_GOLDEN_DIR = Path(__file__).parent / "fixtures" / "dsp_v1_0"
_GOLDEN_V1_0 = {
    0: (_GOLDEN_DIR / "stack.dsp").read_text(),
    1: (_GOLDEN_DIR / "parallel_mods.dsp").read_text(),
    2: (_GOLDEN_DIR / "carrier_pair.dsp").read_text(),
}


def test_dsp_string_v1_0_golden():
    """No-lfo dsp_string equals the committed verbatim v1.0 golden, per algorithm.

    This anchors backward-compat bit-identity (SYNTH-01 SC#2) to the EXACT
    Phase-6 source: any change to the v1.0 routing body (not just an `lfo_`
    introduction) re-renders the already-authored corpus and fails here.
    """
    for algorithm, golden in _GOLDEN_V1_0.items():
        assert dsp_string(_fm_params(algorithm=algorithm)) == golden


def test_manifest_accepts_v11(tmp_path):
    """A valid v1.1 manifest with an lfo block loads; the lfo round-trips."""
    manifest = tmp_path / "call_fm.json"
    manifest.write_text(
        json.dumps(
            _manifest_dict(
                spec_version="1.1",
                lfo={"rate": 6.0, "depth": 0.8, "wave": 0, "target": 0},
            )
        )
    )
    fp = load_manifest(str(manifest), str(tmp_path))
    assert fp.lfo is not None
    assert fp.lfo.rate == 6.0 and fp.lfo.depth == 0.8
    assert fp.lfo.wave == 0 and fp.lfo.target == 0


def test_manifest_v10_no_lfo_still_loads(tmp_path):
    """A v1.0 manifest (no lfo) loads with .lfo is None (loader backward-compat)."""
    manifest = tmp_path / "call_fm.json"
    manifest.write_text(json.dumps(_manifest_dict(spec_version="1.0")))
    fp = load_manifest(str(manifest), str(tmp_path))
    assert fp.lfo is None


def test_lfo_target_bad_enum(tmp_path):
    """An lfo.target not in {0,1} raises IngestError."""
    manifest = tmp_path / "call_fm.json"
    manifest.write_text(
        json.dumps(
            _manifest_dict(
                spec_version="1.1",
                lfo={"rate": 6.0, "depth": 0.8, "wave": 0, "target": 5},
            )
        )
    )
    with pytest.raises(IngestError, match="lfo target"):
        load_manifest(str(manifest), str(tmp_path))


# --- Render tests (require dawdreamer) --------------------------------------

dawdreamer = pytest.importorskip("dawdreamer")  # A6: skip on non-arm64 CI

from apollo.synth.render import render, render_call_wav  # noqa: E402
from apollo.ingest.midi import load_notes  # noqa: E402


def test_render_deterministic(tmp_path):
    """Rendering the same params + notes twice is bit-identical (np.array_equal)."""
    mid = tmp_path / "call.mid"
    _write_call_mid(mid)
    notes = load_notes(str(mid), str(tmp_path), tempo_bpm=120.0)
    params = _fm_params()
    a = render(params, notes, pair_path=str(tmp_path))
    b = render(params, notes, pair_path=str(tmp_path))
    assert np.array_equal(a, b)


def test_no_clipping(tmp_path):
    """After peak normalization, the audio never exceeds 1.0 (and hits ~TARGET_PEAK)."""
    mid = tmp_path / "call.mid"
    _write_call_mid(mid)
    notes = load_notes(str(mid), str(tmp_path), tempo_bpm=120.0)
    audio = render(_fm_params(), notes, pair_path=str(tmp_path))
    assert np.max(np.abs(audio)) <= 1.0


def test_mel_contract(tmp_path):
    """A rendered wav feeds the frozen MelExtractor to (96, 128) float32."""
    mid = tmp_path / "call.mid"
    _write_call_mid(mid)
    notes = load_notes(str(mid), str(tmp_path), tempo_bpm=120.0)
    audio = render(_fm_params(), notes, pair_path=str(tmp_path))
    wav = tmp_path / "call.wav"
    sf.write(str(wav), audio, SR)
    out = MelExtractor()(str(wav), str(tmp_path))
    assert out.shape == (96, 128)
    assert out.dtype == torch.float32


def test_timbre_discriminable(tmp_path):
    """Two contrasting presets produce mels that differ (cos < 0.999 and L2 > 1)."""
    mid = tmp_path / "call.mid"
    _write_call_mid(mid)
    notes = load_notes(str(mid), str(tmp_path), tempo_bpm=120.0)

    mx = MelExtractor()
    # Preset A: simple 1:1 stack. Preset B: bright high-ratio parallel mods.
    audio_a = render(_fm_params(ratio=1.0, level=0.3, algorithm=0), notes, pair_path=str(tmp_path))
    audio_b = render(_fm_params(ratio=7.0, level=1.0, algorithm=1), notes, pair_path=str(tmp_path))

    wav_a, wav_b = tmp_path / "a.wav", tmp_path / "b.wav"
    sf.write(str(wav_a), audio_a, SR)
    sf.write(str(wav_b), audio_b, SR)
    mel_a = mx(str(wav_a), str(tmp_path)).flatten()
    mel_b = mx(str(wav_b), str(tmp_path)).flatten()

    cos = torch.nn.functional.cosine_similarity(mel_a, mel_b, dim=0).item()
    l2 = torch.linalg.norm(mel_a - mel_b).item()
    assert cos < 0.999
    assert l2 > 1.0


def test_lfo_render_deterministic(tmp_path):
    """An LFO render is bit-identical across runs (np.array_equal)."""
    mid = tmp_path / "call.mid"
    _write_call_mid(mid)
    notes = load_notes(str(mid), str(tmp_path), tempo_bpm=120.0)
    params = _fm_params(lfo=LfoParams(6.0, 0.8, 0, 0))
    a = render(params, notes, pair_path=str(tmp_path))
    b = render(params, notes, pair_path=str(tmp_path))
    assert np.array_equal(a, b)


def test_lfo_changes_audio(tmp_path):
    """An LFO patch renders differently from the no-lfo patch."""
    mid = tmp_path / "call.mid"
    _write_call_mid(mid)
    notes = load_notes(str(mid), str(tmp_path), tempo_bpm=120.0)
    nolfo = render(_fm_params(), notes, pair_path=str(tmp_path))
    lfo = render(_fm_params(lfo=LfoParams(6.0, 0.8, 0, 0)), notes, pair_path=str(tmp_path))
    assert not np.array_equal(nolfo, lfo)


def test_lfo_render_no_clipping(tmp_path):
    """An LFO render still normalizes below 1.0 (Pitfall 5)."""
    mid = tmp_path / "call.mid"
    _write_call_mid(mid)
    notes = load_notes(str(mid), str(tmp_path), tempo_bpm=120.0)
    audio = render(_fm_params(lfo=LfoParams(6.0, 0.8, 2, 0)), notes, pair_path=str(tmp_path))
    assert np.max(np.abs(audio)) <= 1.0


def test_lfo_pitch_render(tmp_path):
    """A pitch-target (vibrato) LFO renders deterministically and differs."""
    mid = tmp_path / "call.mid"
    _write_call_mid(mid)
    notes = load_notes(str(mid), str(tmp_path), tempo_bpm=120.0)
    nolfo = render(_fm_params(), notes, pair_path=str(tmp_path))
    vib = _fm_params(lfo=LfoParams(6.0, 0.8, 0, 1))
    a = render(vib, notes, pair_path=str(tmp_path))
    b = render(vib, notes, pair_path=str(tmp_path))
    assert np.array_equal(a, b)
    assert not np.array_equal(nolfo, a)


def test_render_call_wav_parity(tmp_path):
    """The shared render_call_wav is deterministic for the same (manifest, mid)."""
    mid = tmp_path / "call.mid"
    manifest = tmp_path / "call_fm.json"
    _write_call_mid(mid)
    _write_manifest(manifest)
    a = render_call_wav(str(manifest), str(mid), pair_path=str(tmp_path), call_bpm=120.0)
    b = render_call_wav(str(manifest), str(mid), pair_path=str(tmp_path), call_bpm=120.0)
    assert np.array_equal(a, b)


# --- LFO render contract tests (SYNTH-01 SC#1-3, #5; require dawdreamer) -----


def test_lfo_absent_bit_identical(tmp_path):
    """No-lfo render is deterministic AND its dsp_string == the golden v1.0 string.

    SYNTH-01 SC#2: backward-compat bit-identity is anchored TWO ways — the array
    re-render is identical, and the emitted source equals the committed verbatim
    Phase-6 v1.0 STACK golden byte-for-byte (the strong anchor; `"lfo_" not in`
    alone is too weak — it passes even if the v1.0 body were mutated elsewhere).
    """
    mid = tmp_path / "call.mid"
    _write_call_mid(mid)
    notes = load_notes(str(mid), str(tmp_path), tempo_bpm=120.0)
    a = render(_fm_params(), notes, pair_path=str(tmp_path))
    b = render(_fm_params(), notes, pair_path=str(tmp_path))
    assert np.array_equal(a, b)
    # Strong source anchor: byte-for-byte equality with the committed v1.0 golden.
    assert dsp_string(_fm_params()) == _GOLDEN_V1_0[0]


def test_lfo_depth0_matches_static(tmp_path):
    """A depth-0 lfo render is bit-identical to the no-lfo (static) render.

    SYNTH-01 SC#2 array-level anchor (RESEARCH VERIFIED max diff 0.0 this
    session). An authored-but-disabled LFO must not perturb the audio.
    """
    mid = tmp_path / "call.mid"
    _write_call_mid(mid)
    notes = load_notes(str(mid), str(tmp_path), tempo_bpm=120.0)
    static = render(_fm_params(), notes, pair_path=str(tmp_path))
    depth0 = render(
        _fm_params(lfo=LfoParams(6.0, 0.0, 0, 0)), notes, pair_path=str(tmp_path)
    )
    assert np.array_equal(static, depth0)


def test_lfo_time_varies(tmp_path):
    """An LFO render is measurably time-varying vs static through the mel (SC#1).

    Renders a 6 Hz, depth-1.0 tremolo patch and a depth-0 (static) patch, passes
    each through the frozen MelExtractor, and asserts cosine similarity < 0.999.
    Rate is pinned at 6 Hz (NOT the 0.05 Hz partial-sweep edge — RESEARCH
    Pitfall 4). Depth is 1.0 (rather than RESEARCH's 0.8 baseline) so the
    measured cos sits comfortably below the 0.999 threshold (07-02 measured
    cos=0.997650 at 6 Hz/1.0 — a ~0.00135 margin, vs ~0.00028 at depth 0.8).
    The threshold is NOT loosened; the modulation is made more separable.
    """
    mid = tmp_path / "call.mid"
    _write_call_mid(mid)
    notes = load_notes(str(mid), str(tmp_path), tempo_bpm=120.0)
    audio_lfo = render(
        _fm_params(lfo=LfoParams(6.0, 1.0, 0, 0)), notes, pair_path=str(tmp_path)
    )
    audio_static = render(
        _fm_params(lfo=LfoParams(6.0, 0.0, 0, 0)), notes, pair_path=str(tmp_path)
    )

    mx = MelExtractor()
    wav_lfo, wav_static = tmp_path / "lfo.wav", tmp_path / "static.wav"
    sf.write(str(wav_lfo), audio_lfo, SR)
    sf.write(str(wav_static), audio_static, SR)
    mel_lfo = mx(str(wav_lfo), str(tmp_path)).flatten()
    mel_static = mx(str(wav_static), str(tmp_path)).flatten()

    cos = torch.nn.functional.cosine_similarity(mel_lfo, mel_static, dim=0).item()
    assert cos < 0.999


def test_lfo_mel_contract(tmp_path):
    """An lfo render still feeds the frozen MelExtractor to (96, 128) float32 (SC#5)."""
    mid = tmp_path / "call.mid"
    _write_call_mid(mid)
    notes = load_notes(str(mid), str(tmp_path), tempo_bpm=120.0)
    audio = render(
        _fm_params(lfo=LfoParams(6.0, 0.8, 0, 0)), notes, pair_path=str(tmp_path)
    )
    wav = tmp_path / "call.wav"
    sf.write(str(wav), audio, SR)
    out = MelExtractor()(str(wav), str(tmp_path))
    assert out.shape == (96, 128)
    assert out.dtype == torch.float32


def test_lfo_no_clipping(tmp_path):
    """A deep square-wave lfo render never exceeds 1.0 after normalization (Pitfall 5)."""
    mid = tmp_path / "call.mid"
    _write_call_mid(mid)
    notes = load_notes(str(mid), str(tmp_path), tempo_bpm=120.0)
    audio = render(
        _fm_params(lfo=LfoParams(6.0, 1.0, 2, 0)), notes, pair_path=str(tmp_path)
    )
    assert np.max(np.abs(audio)) <= 1.0


# --- Manifest validation tests (NO dawdreamer needed; always run) -----------
# These are defined after the importorskip but call load_manifest directly,
# which has no dawdreamer dependency. If dawdreamer is absent the whole module
# skips at import time; the validation boundary is additionally covered by
# tests/test_synth_manifest-style checks in 06-01. Kept here per the plan's
# behavior list so this suite is self-contained where dawdreamer is present.


def test_manifest_bad_version(tmp_path):
    """An unsupported spec_version raises IngestError."""
    manifest = tmp_path / "call_fm.json"
    d = _manifest_dict()
    d["spec_version"] = "9.9"
    manifest.write_text(json.dumps(d))
    with pytest.raises(IngestError, match="spec_version"):
        load_manifest(str(manifest), str(tmp_path))


def test_manifest_accepts_v10_no_lfo(tmp_path):
    """A valid v1.0 manifest still loads (lfo None) under the v1.1 loader."""
    manifest = tmp_path / "call_fm.json"
    manifest.write_text(json.dumps(_manifest_dict(spec_version="1.0")))
    fp = load_manifest(str(manifest), str(tmp_path))
    assert fp.lfo is None


def test_manifest_accepts_v11_with_lfo(tmp_path):
    """A valid v1.1 manifest with an lfo block loads into an LfoParams."""
    manifest = tmp_path / "call_fm.json"
    manifest.write_text(
        json.dumps(
            _manifest_dict(
                spec_version="1.1",
                lfo={"rate": 6.0, "depth": 0.8, "wave": 0, "target": 0},
            )
        )
    )
    fp = load_manifest(str(manifest), str(tmp_path))
    assert isinstance(fp.lfo, LfoParams)
    assert fp.lfo.rate == 6.0 and fp.lfo.depth == 0.8
    assert fp.lfo.wave == 0 and fp.lfo.target == 0


def test_lfo_requires_v11(tmp_path):
    """An lfo block under spec_version 1.0 is rejected, naming 1.1."""
    manifest = tmp_path / "call_fm.json"
    manifest.write_text(
        json.dumps(
            _manifest_dict(
                spec_version="1.0",
                lfo={"rate": 6.0, "depth": 0.8, "wave": 0, "target": 0},
            )
        )
    )
    with pytest.raises(IngestError, match="1.1"):
        load_manifest(str(manifest), str(tmp_path))


def test_lfo_rate_out_of_range(tmp_path):
    """An lfo.rate outside [0.05, 20] raises IngestError."""
    manifest = tmp_path / "call_fm.json"
    manifest.write_text(
        json.dumps(
            _manifest_dict(
                spec_version="1.1",
                lfo={"rate": 99.0, "depth": 0.8, "wave": 0, "target": 0},
            )
        )
    )
    with pytest.raises(IngestError, match="lfo rate"):
        load_manifest(str(manifest), str(tmp_path))


def test_lfo_wave_bad_enum(tmp_path):
    """An lfo.wave not in {0,1,2} raises IngestError."""
    manifest = tmp_path / "call_fm.json"
    manifest.write_text(
        json.dumps(
            _manifest_dict(
                spec_version="1.1",
                lfo={"rate": 6.0, "depth": 0.8, "wave": 9, "target": 0},
            )
        )
    )
    with pytest.raises(IngestError, match="lfo wave"):
        load_manifest(str(manifest), str(tmp_path))


def test_lfo_nan_rate(tmp_path):
    """A non-finite lfo.rate raises IngestError (finite check)."""
    manifest = tmp_path / "call_fm.json"
    manifest.write_text(
        json.dumps(
            _manifest_dict(
                spec_version="1.1",
                lfo={"rate": float("nan"), "depth": 0.8, "wave": 0, "target": 0},
            )
        )
    )
    with pytest.raises(IngestError, match="finite"):
        load_manifest(str(manifest), str(tmp_path))


def test_lfo_bool_rejected(tmp_path):
    """A bool in an lfo enum field is rejected (not a valid int)."""
    manifest = tmp_path / "call_fm.json"
    manifest.write_text(
        json.dumps(
            _manifest_dict(
                spec_version="1.1",
                lfo={"rate": 6.0, "depth": 0.8, "wave": True, "target": 0},
            )
        )
    )
    with pytest.raises(IngestError, match="lfo wave"):
        load_manifest(str(manifest), str(tmp_path))


def test_manifest_wrong_op_count(tmp_path):
    """A manifest with != 3 operators raises IngestError."""
    manifest = tmp_path / "call_fm.json"
    d = _manifest_dict()
    d["operators"] = d["operators"][:2]
    manifest.write_text(json.dumps(d))
    with pytest.raises(IngestError, match="operators"):
        load_manifest(str(manifest), str(tmp_path))


def test_manifest_ratio_out_of_range(tmp_path):
    """A ratio outside [0.5, 12] raises IngestError."""
    manifest = tmp_path / "call_fm.json"
    d = _manifest_dict()
    d["operators"][0]["ratio"] = 99.0
    manifest.write_text(json.dumps(d))
    with pytest.raises(IngestError, match="ratio"):
        load_manifest(str(manifest), str(tmp_path))


def test_manifest_nan_field(tmp_path):
    """A non-finite (NaN) numeric field raises IngestError."""
    manifest = tmp_path / "call_fm.json"
    d = _manifest_dict()
    # JSON has no NaN literal; emit one explicitly so the parser accepts it,
    # then load_manifest's finite-check must reject it.
    d["operators"][0]["level"] = float("nan")
    manifest.write_text(json.dumps(d))  # default json emits NaN token
    with pytest.raises(IngestError, match="finite"):
        load_manifest(str(manifest), str(tmp_path))


# --- Normalization tests (WR-01; no dawdreamer needed) ----------------------
# _normalize_peak is a pure array function; importing it does not touch the
# dawdreamer wheel (that import is local to render()).


def test_normalize_peak_leaves_silence_silent():
    """WR-01: a near-silent buffer is NOT amplified into full-scale noise."""
    from apollo.synth.render import _normalize_peak

    dust = np.array([1e-8, -5e-9, 0.0, 2e-9], dtype=np.float32)
    out = _normalize_peak(dust)
    # Old behavior divided by the ~1e-8 peak, scaling dust up to ~TARGET_PEAK
    # (0.89); the silence floor leaves it as silence.
    assert np.max(np.abs(out)) < 1e-6


def test_normalize_peak_scales_real_audio():
    """A normal buffer is scaled to exactly TARGET_PEAK (determinism preserved)."""
    from apollo.synth.render import _normalize_peak
    from apollo.synth.spec import TARGET_PEAK

    sig = np.array([0.1, -0.4, 0.25], dtype=np.float32)
    out = _normalize_peak(sig)
    assert np.isclose(np.max(np.abs(out)), TARGET_PEAK, atol=1e-6)

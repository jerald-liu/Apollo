"""Deterministic headless 3-operator FM renderer (DawDreamer + Faust).

Turns a validated `FmParams` patch + a list of monophonic `Note`s into a
normalized mono audio array, bit-deterministically (spike 001 confirmed
`np.array_equal` true on re-render). The array feeds the FROZEN COND-01
`apollo.ingest.audio.MelExtractor` unchanged to its `(96, 128)` contract; the
renderer therefore peak-normalizes with headroom BEFORE any PCM write so the
mel never sees clipped audio (spike saw peaks > 1.0 that `soundfile` clips).

Design (see .planning/phases/06-synth-independent-corpus-rendering/06-RESEARCH.md
§"MIDI -> Render Path", §"Determinism & Normalization", §"Train/Serve Parity
Wiring"):

  - MIDI parsing is delegated to `apollo.ingest.midi.load_notes` — the ONE
    validation path (monophony / tempo / empty / DoS guards). The renderer never
    re-parses MIDI with raw pretty_midi.
  - The Faust patch comes only from `apollo.synth.spec.dsp_string` (numeric-only;
    no manifest string ever reaches the DSP source).
  - Per-operator params are set by integer index resolved AT RUNTIME from
    `synth.get_parameters_description()` — never a path string, never a hardcoded
    index (the polyphony landmine; spike RuntimeError under `num_voices`).
  - Render duration is derived deterministically and capped at
    `MAX_RENDER_SECONDS` (mirrors MelExtractor.MAX_WAV_SECONDS; T-06-06 DoS).
  - Normalization is a single scalar peak gain (deterministic, linear) — no
    RMS / loudness / compressor, which are non-linear or content-dependent and
    would distort the timbre-conditioning signal.

`render_call_wav` is the SINGLE shared render entrypoint: both the corpus render
CLI (`apollo.scripts.render_corpus`) and inference (`generate.py`, Plan 06-03)
call it, guaranteeing the training corpus and inference-time calls are rendered
bit-identically (train/serve parity — the domain gap DATA-06 forbids).
"""

from __future__ import annotations

import contextlib
import io

import numpy as np

from apollo.ingest.errors import IngestError
from apollo.ingest.midi import load_notes
from apollo.synth.manifest import load_manifest
from apollo.synth.spec import (
    BLOCK,
    NUM_VOICES,
    SR,
    TARGET_PEAK,
    FmParams,
    dsp_string,
)

# Render-duration cap (T-06-06 DoS). Mirrors MelExtractor.MAX_WAV_SECONDS so a
# crafted manifest/MIDI can never request an unbounded render before the engine
# runs. MelExtractor truncates anything longer anyway.
MAX_RENDER_SECONDS = 30.0  # mirror MelExtractor.MAX_WAV_SECONDS (T-01-08 class)

# Per-operator settable slider fields, mapped to the OperatorParams attribute.
# Only `ratio` and `level` are exposed as runtime-settable Faust hsliders by
# spec.dsp_string; the ADSR fields (attack/decay/sustain/release) are compiled
# as numeric literals INSIDE `en.adsr(...)` at DSP-string-generation time (so
# they are baked into the patch from the manifest at compile time — they take
# effect, they are just not runtime parameters). `freq`/`gain`/`gate` are
# MIDI-owned and are not set here.
_OP_SLIDER_FIELDS = ("ratio", "level")


def _build_name_index_map(synth) -> dict[str, int]:
    """Resolve Faust slider NAME -> integer index from the engine description.

    LANDMINE (spike): under `num_voices` the reported `name` is the mangled poly
    path (`/Polyphonic/Voices/dawdreamer/<slider>`) and setting by path
    RuntimeErrors; indices are assigned by Faust declaration order and shift as
    the patch grows. We never hardcode an index — we match on the unmangled
    slider name, which DawDreamer exposes in the `label` field (and recover it
    from the trailing path segment of `name` as a fallback).
    """
    name_to_index: dict[str, int] = {}
    for desc in synth.get_parameters_description():
        idx = desc["index"]
        label = desc.get("label")
        if label:
            name_to_index[label] = idx
        # Fallback: trailing segment of the (possibly mangled) name/path.
        raw = desc.get("name") or ""
        if raw:
            name_to_index.setdefault(raw.rsplit("/", 1)[-1], idx)
    return name_to_index


def render(params: FmParams, notes, *, pair_path: str) -> np.ndarray:
    """Render `params` + `notes` to a normalized mono float32 audio array.

    Deterministic: identical inputs yield a bit-identical array (`np.array_equal`).
    Raises `IngestError(pair_path, ...)` if the derived render duration exceeds
    `MAX_RENDER_SECONDS`.
    """
    import dawdreamer as dd  # local import; heavy native wheel (no __version__)

    if not notes:
        raise IngestError(pair_path, "render requires at least one note")

    # --- Derive render duration deterministically (RESEARCH §"Render duration").
    # Cover the longest release tail so the envelope is not cut mid-decay;
    # MelExtractor pads short clips, so erring long is safe and under-rendering
    # (clipping the tail) is the real risk.
    max_release = max(op.release for op in params.operators)
    dur = max(n.end for n in notes) + max_release + 0.1

    # --- Cap (T-06-06 DoS) — before the engine runs.
    if dur > MAX_RENDER_SECONDS:
        raise IngestError(
            pair_path,
            f"render duration {dur:.2f}s exceeds cap ({MAX_RENDER_SECONDS}s)",
        )

    # --- Build the engine + Faust processor. The benign `undefined symbol :
    # effect` warning is emitted by the poly factory to stderr; redirect it so
    # it doesn't pollute CLI output (T-06-10 accept — cosmetic only).
    with contextlib.redirect_stderr(io.StringIO()):
        engine = dd.RenderEngine(SR, BLOCK)
        synth = engine.make_faust_processor("fm")
        synth.set_dsp_string(dsp_string(params))
        synth.num_voices = NUM_VOICES  # overlapping note releases must not cut

        # --- LANDMINE: resolve param indices at runtime; set by int index only.
        name_to_index = _build_name_index_map(synth)
        for i, op in enumerate(params.operators, start=1):
            for field in _OP_SLIDER_FIELDS:
                slider = f"op{i}_{field}"
                if slider not in name_to_index:
                    raise IngestError(
                        pair_path,
                        f"render engine is missing expected param {slider!r}",
                    )
                synth.set_parameter(int(name_to_index[slider]), float(getattr(op, field)))

        # --- Notes: velocity passes straight through (DawDreamer maps
        # velocity -> gain internally; do NOT double-apply manifest gain).
        for n in notes:
            synth.add_midi_note(n.pitch, n.velocity, n.start, n.end - n.start)

        engine.load_graph([(synth, [])])
        engine.render(dur)
        audio = engine.get_audio()  # (channels, samples)

    audio = np.asarray(audio, dtype=np.float32)

    # --- Mono: take a single channel (removes L/R asymmetry as a determinism
    # variable; MelExtractor mono-mixes anyway).
    if audio.ndim > 1:
        audio = audio[0]

    # --- Normalize: scalar peak gain with headroom (deterministic, linear).
    # Pure gain preserves spectral shape, so the mel timbre signal survives.
    peak = float(np.max(np.abs(audio)))
    audio = audio / max(peak, 1e-9) * TARGET_PEAK

    return audio.astype(np.float32, copy=False)


def render_call_wav(
    manifest_path: str,
    mid_path: str,
    *,
    pair_path: str,
    call_bpm: float = 120.0,
    notes=None,
) -> np.ndarray:
    """The single shared render entrypoint (train/serve parity).

    Loads FM params via `load_manifest`, parses the call MIDI via the shared
    `load_notes` (unless a pre-parsed `notes` list is supplied — generate.py
    passes the SAME parsed `call_notes` to avoid double-parsing the MIDI under a
    different tempo assumption), and returns the normalized audio array from
    `render`.

    Both `render_corpus.py` and `generate.py` MUST call this one function so the
    corpus and inference renders are bit-identical.
    """
    params = load_manifest(manifest_path, pair_path)
    if notes is None:
        notes = load_notes(mid_path, pair_path, tempo_bpm=call_bpm)
    return render(params, notes, pair_path=pair_path)

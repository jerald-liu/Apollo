# Apollo v1 Corpus Authoring Conventions

This directory holds hand-authored call/response pairs that train the Apollo v1 model. Each pair's timbre is a **hand-authored FM-parameter manifest** (`call_fm.json`) rendered by Apollo's own headless synth — there is **no Ableton bounce step**. Read this before authoring any pair.

## Minimum corpus size

At least **30 pairs** must exist in this directory before the first real training run (`apollo/scripts/train.py`). This is requirement **DATA-05**. The gate counts **authored pairs** (`call.mid` + `call_fm.json` + `response.mid`), **not** rendered `call.wav` files — `call.wav` is a derived build artifact that is reproduced deterministically from `call_fm.json` + `call.mid`.

## Per-pair file layout (DATA-02, superseded by DATA-06)

Each pair lives at `data/pairs/NNN/`. The **authored** files are:

- `call.mid` — MIDI of the call phrase (monophonic, 120 BPM)
- `call_fm.json` — hand-authored FM-parameter manifest defining the call's timbre (see schema below)
- `response.mid` — MIDI of the response phrase (monophonic, 120 BPM)

The **derived** file (rendered, gitignored, never hand-authored):

- `call.wav` — rendered from `call.mid` + `call_fm.json` by `apollo/scripts/render_corpus.py`. Deterministic: same manifest + MIDI → bit-identical wav.

`NNN` is zero-padded sequential (`001`, `002`, ..., `030`, ...).

> **`call_fm.json` is NOT `apollo/eval/render_manifest.py`.** `call_fm.json` is a *per-pair FM-parameter* manifest consumed by the synth renderer. `apollo/eval/render_manifest.py` is the unrelated **M4L eval run manifest** (one entry per held-out pair, used by the evaluation loop). Different purpose entirely — do not conflate the two "manifests".

## Authoring conventions (locked decisions)

| Convention | Value | Source |
|---|---|---|
| Tempo | **120 BPM** exactly. The ingest pipeline enforces ±2 BPM tolerance (`apollo/ingest/midi.py` `load_notes`). | D-01 |
| Timbre | **Vary across pairs** via the hand-authored FM-param manifest (`call_fm.json`) — bright plucks, soft pads, percussive FM tones, etc. The model must learn that the right response depends on timbre. The v1 engine is a **3-operator FM family** (DawDreamer + Faust); Apollo's synth is **not** a clone of Ableton's 4-operator / 11-algorithm Operator — its sound is its own. | D-02 |
| Key / scale | **Free choice per pair.** The tokenizer uses absolute pitch bins, so key variety is not a structural problem. | D-03 |
| Gesture length | **0.5–1.5 seconds, 2–6 notes per side.** Fits within `max_seq_len=64`. | D-04 |
| Response relationship | **Varied per pair** — echo, contrast, continuation, complement. No labeling required. | D-05 |
| Call vs. response timbre | **Same or different is free choice per pair.** No constraint. | D-06 |
| Pitch-shift augmentation | **Deferred.** Do not author pitch-shifted variants. | D-07 |

## The `call_fm.json` schema (spec_version "1.0")

The authoritative spec lives in `apollo/synth/spec.py` (`SPEC_VERSION`, `Algorithm`, `FmParams`/`OperatorParams`); the validator is `apollo/synth/manifest.py`. A manifest is a JSON object:

```json
{
  "spec_version": "1.0",
  "algorithm": 0,
  "operators": [
    { "ratio": 1.0, "level": 1.0, "attack": 0.005, "decay": 0.12, "sustain": 0.7, "release": 0.20 },
    { "ratio": 2.0, "level": 0.8, "attack": 0.005, "decay": 0.10, "sustain": 0.5, "release": 0.15 },
    { "ratio": 3.0, "level": 0.4, "attack": 0.002, "decay": 0.08, "sustain": 0.3, "release": 0.10 }
  ],
  "gain": 0.5
}
```

| Field | Type | Range | Notes |
|---|---|---|---|
| `spec_version` | string | must equal `"1.0"` | Mismatch → `IngestError`; an old corpus cannot silently re-render under a changed spec. |
| `algorithm` | int | `0..2` | Routing topology: **0 = STACK** (3→2→1, one carrier), **1 = PARALLEL_MODS** ((2+3)→1), **2 = CARRIER_PAIR** (3→1 plus op2 as an independent carrier). |
| `operators` | array | **exactly 3** | One entry per operator; any other count → `IngestError`. |
| `operators[].ratio` | float | `0.5 .. 12.0` | Oscillator frequency multiplier of the note fundamental. |
| `operators[].level` | float | `0.0 .. 1.0` | Operator output / modulation depth. |
| `operators[].attack` | float (s) | `0.0 .. 2.0` | ADSR attack. |
| `operators[].decay` | float (s) | `0.0 .. 2.0` | ADSR decay. |
| `operators[].sustain` | float | `0.0 .. 1.0` | ADSR sustain level. |
| `operators[].release` | float (s) | `0.0 .. 2.0` | ADSR release. |
| `gain` | float | `0.0 .. 1.0` | Master output gain (pre-normalization). |

## Authoring workflow (FM-manifest, no Ableton)

1. Author the **call** phrase as `call.mid` inside `data/pairs/NNN/` (2–6 notes, 0.5–1.5 s, monophonic, at 120 BPM).
2. Hand-author `call_fm.json` beside it, defining the call's timbre per the schema above (pick an `algorithm`, set the three operators' `ratio`/`level`/ADSR, set `gain`).
3. Author the **response** phrase as `response.mid` (2–6 notes, 0.5–1.5 s, monophonic, at 120 BPM).
4. Render `call.wav` for the whole corpus:
   ```
   .venv/bin/python -m apollo.scripts.render_corpus data/pairs/
   ```
   This renders `call.wav` deterministically from each pair's `call.mid` + `call_fm.json`. The same renderer (`apollo.synth.render.render_call_wav`) is used at inference time by `generate.py`, so training and serving share one engine (no domain gap — DATA-06).
5. Verify: `data/pairs/NNN/` now contains the authored `call.mid`, `call_fm.json`, `response.mid`, plus the derived (gitignored) `call.wav`.

> At inference, you do **not** pre-render `call.wav` — `generate.py` renders the call audio on-the-fly from `call_fm.json` via the same `render_call_wav`.

## Known limitation: envelope-driven rhythm

FM envelopes can produce perceived rhythm (e.g. a fast-decaying ADSR creating a pulse on a held note) without any MIDI note events. The model receives the mel spectrogram of `call.wav` and can "hear" this timbral rhythm, but **the response channel is MIDI-only** — the model can only answer with note events, not synthesis parameters. A call with strong envelope-driven pulse may not get a response that engages with that texture.

**Practical guidance:** For v1, prefer calls where rhythmic intent is expressed primarily through note events rather than synthesis modulation. Calls that rely heavily on envelope-driven rhythm will produce responses that are rhythmically "straight" relative to the call's timbral pulse. This asymmetry is a known v1 limitation, deferred to a later milestone.

## Validation

The ingest pipeline (`apollo/scripts/ingest_corpus.py`) and the renderer (`apollo/scripts/render_corpus.py`) both fail loudly on any non-conforming pair:

- Missing files → `IngestError` reports the offending pair
- Tempo outside 120 ± 2 BPM → `IngestError`
- Empty MIDI (zero notes) → `IngestError`
- Polyphony (overlapping notes on same track) → `IngestError`
- Malformed `call_fm.json` (bad `spec_version`, wrong operator count, out-of-range / non-finite / non-numeric fields) → `render_corpus` raises `IngestError` naming the offending pair

Run, after authoring:

```
.venv/bin/python -m apollo.scripts.ingest_corpus data/pairs/
.venv/bin/python -m apollo.scripts.render_corpus data/pairs/
```

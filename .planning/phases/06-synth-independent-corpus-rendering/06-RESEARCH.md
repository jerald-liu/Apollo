# Phase 6: Synth-Independent Corpus Rendering - Research

**Researched:** 2026-06-02
**Domain:** Headless FM synthesis (DawDreamer + Faust), deterministic audio rendering, train/serve parity
**Confidence:** HIGH (feasibility pre-proven by spikes 001/002; this research is design, not validation)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Engine:** DawDreamer + Faust, headless. `dawdreamer==0.8.3` arm64/Py3.11 wheel (validated). `[VERIFIED: PyPI — 0.8.3 is still latest as of 2026-06]`
- **Topology:** **3 operators** for v1. Full 4-op/11-algorithm/filter/LFO is deferred to `SEED-009`.
- **Do NOT clone Operator's sound.** Provide a controllable FM family only.
- **Per-pair timbre = hand-authored FM-param manifest** (JSON or code). No synth UI in v1.
- **Single source of truth:** manifest format + FM param schema + algorithm set + envelope semantics live in **one place** so Phase 5's browser synth implements the same spec.
- **Bit-deterministic:** same manifest + MIDI → identical `call.wav`.
- **Feed `MelExtractor` (COND-01) unchanged** to its `(96,128)` contract. No downstream pipeline changes.
- **Same engine + manifest render inference-time calls** (train/serve parity).
- **Normalize / headroom** before writing PCM (spike 001 saw peaks 1.13–1.19 that `soundfile` clips).
- **Docs to reconcile:** update `data/pairs/CORPUS-CONVENTIONS.md`; amend `REQUIREMENTS.md` DATA-01/02 wording; phase **blocks DATA-05**.
- **Build gotchas (MUST honor):** Faust poly params via integer index not path string; filter benign `undefined symbol : effect` warning; `dawdreamer.__version__` does not exist.

### Claude's Discretion
- Exact manifest JSON schema fields and the FM parameter set within the 3-op envelope.
- Where the FM spec module lives in `apollo/` and the render CLI surface/name.
- How `call.mid` is parsed into note events (existing `apollo/ingest/midi.py` vs `pretty_midi`); render sample rate (renderer SR free; `MelExtractor` resamples to 22050).
- Reuse vs. extension of `apollo/eval/render_manifest.py` naming concepts (distinct purpose — avoid confusion).

### Deferred Ideas (OUT OF SCOPE)
- Full 4-op / 11-algorithm / filter / LFO engine → `SEED-009`.
- Phase 5 browser-synth implementation of the shared spec → Phase 5.
- FM patch generation head (model outputs timbre) → `SEED-001` / backlog 999.1.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DATA-06 | Render `call.wav` **deterministically** from a per-pair FM manifest using a headless **no-Ableton** 3-op DawDreamer+Faust synth; output feeds COND-01 unchanged; **same engine renders inference-time calls** (no domain gap). Supersedes DATA-01/02 manual-bounce premise. | Sections "FM Spec Module", "Manifest Schema", "3-Op Faust Patch", "MIDI→Render Path", "Determinism & Normalization", "Train/Serve Parity". |
</phase_requirements>

## Summary

Feasibility is settled. Spike 001 proved DawDreamer 0.8.3 + a 2-op Faust patch renders MIDI→wav bit-deterministically on Apple Silicon with no Ableton; spike 002 proved that wav flows through the **production** `MelExtractor` to the exact `(96,128)` COND-01 contract with timbre-discriminable mels (within-preset cos 1.00, across-preset 0.85). This phase is therefore **purely a design + wiring exercise**: extend the proven 2-op skeleton to 3 operators, define a hand-authorable per-pair manifest, fold the param schema + algorithm set + envelope semantics into one Python module that is the single source of truth (which Phase 5's browser synth will later implement), and wire that engine into both corpus ingest and `generate.py` so training and serving share one renderer.

The central architectural move is a **`FmSpec` module** (`apollo/synth/`) that owns three things — the parameter schema (with ranges/defaults), the algorithm set (operator routing topologies), and envelope semantics — plus a `render(manifest, notes) -> np.ndarray` function. Everything else (the corpus render CLI, the inference hook in `generate.py`, the Phase 5 browser synth) is a *consumer* of this module. Keeping the spec authoritative in one file is what guarantees train/serve parity and lets the JS synth be validated against the Python engine later.

**Primary recommendation:** Build `apollo/synth/` with three files — `spec.py` (frozen dataclass schema + algorithm enum + the Faust DSP-string generator), `render.py` (manifest+notes → deterministic normalized audio), `manifest.py` (load/validate/version the per-pair JSON). Pin a single algorithm set of **3 fixed topologies** (not a free routing matrix). Reuse `apollo/ingest/midi.py::load_notes` for note parsing so monophony/tempo guards already apply. Hook `render.py` into `generate.py` so `call.wav` is rendered on-the-fly at inference from `call_fm.json` instead of being supplied as a file.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| FM parameter schema + algorithm set + envelope semantics | `apollo/synth/spec.py` (spec tier) | — | Single source of truth; Phase 5 JS synth mirrors this, not the renderer. |
| Faust DSP-string generation (3-op) | `apollo/synth/spec.py` | — | DSP is a *projection* of the spec; co-locating prevents drift between schema and patch. |
| Manifest load / validate / version | `apollo/synth/manifest.py` | — | Input-validation boundary (security tier); fail-loud via `IngestError`. |
| MIDI → note events | `apollo/ingest/midi.py::load_notes` (ingest tier) | `apollo/synth/render.py` adapter | Reuse existing monophony/tempo/DoS guards; don't re-parse with raw `pretty_midi`. |
| Deterministic render + normalization | `apollo/synth/render.py` | — | Owns DawDreamer engine lifecycle, block size, render length, headroom. |
| Corpus-time rendering (batch over `data/pairs/`) | render CLI (`apollo/scripts/render_corpus.py`) | `apollo/synth/render.py` | Authoring/ingest workflow surface. |
| Inference-time call rendering | `apollo/scripts/generate.py` | `apollo/synth/render.py` | Train/serve parity: same engine + manifest format. |
| Mel extraction | `apollo/ingest/audio.py::MelExtractor` (unchanged) | — | COND-01 contract is frozen; renderer must satisfy it, not modify it. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| dawdreamer | `==0.8.3` | Headless render engine + built-in Faust processor | Spike-validated arm64/Py3.11 wheel; latest on PyPI. `[VERIFIED: PyPI]` `[CITED: spike-findings synth-independent-rendering.md]` |
| Faust (bundled in dawdreamer) | bundled | FM DSP via `set_dsp_string` | No separate Faust toolchain needed — compiled in-process by dawdreamer. `[CITED: spike 001]` |
| soundfile | `>=0.12` (already dep) | Write `call.wav` (`audio.T`) | Already the project's WAV I/O; `MelExtractor` reads via it too. `[VERIFIED: pyproject.toml]` |
| numpy | `>=1.24` (already dep) | audio array math, normalization, determinism check | Already a dep. `[VERIFIED: pyproject.toml]` |
| pretty_midi | `>=0.2.11` (already dep, via `load_notes`) | MIDI parse | Reuse through `apollo/ingest/midi.py`. `[VERIFIED: pyproject.toml]` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Reuse `load_notes` for note events | raw `pretty_midi` in `render.py` | Raw parse loses the monophony/tempo/empty/DoS guards already enforced in ingest. Reuse keeps one validation path. |
| Faust `set_dsp_string` | A precompiled `.dsp` file / libfaust box API | DSP string is what the spike proved and keeps the patch versioned in Python next to the schema. No reason to split. |
| 3 fixed algorithm topologies | Free per-operator routing matrix | Free routing explodes the conditioning dimensionality the small mel encoder must learn (see decision rationale §2). Fixed set is deliberately minimal and hand-authorable. |

**Installation (adds one dep):**
```toml
# pyproject.toml [project].dependencies — add:
"dawdreamer==0.8.3",
```
Pin exactly (`==`): it is a heavy native wheel with platform-specific builds; an accidental minor bump could change DSP/render behavior and break determinism reproducibility of an already-authored corpus. `[VERIFIED: PyPI shows 0.8.3 latest; arm64/Py3.11 wheel]`

## FM Spec Module (single source of truth)

The contract surface Phase 5 must mirror. Recommended layout:

```
apollo/synth/
├── __init__.py
├── spec.py        # FmParams dataclass, Algorithm enum, SPEC_VERSION, dsp_string(params) -> str
├── manifest.py    # load_manifest(path) -> FmParams, validate + version check, IngestError on bad input
└── render.py      # render(params, notes, *, sr, dur) -> np.ndarray; render_call_wav(...) convenience
```

**`spec.py` contract surface** (what the JS synth re-implements):
- `SPEC_VERSION: str` — semantic version of the FM spec (e.g. `"1.0"`); written into every manifest.
- `class Algorithm(IntEnum)` — the small fixed set of 3-op routings (see "3-Op Faust Patch" for the proposed set).
- `@dataclass(frozen=True) class FmParams` — the full parameter set with field-level ranges/defaults.
- `def dsp_string(p: FmParams) -> str` — deterministic Faust DSP source for the selected algorithm + params. **This is the only place a Faust string is constructed.**
- `PARAM_INDEX: dict[str, int]` or a documented ordering — to honor the integer-index landmine (params set by position, not path).

**Why one module:** the decision note's open conflict #1 — two renderers (Python corpus + JS browser) must produce matching audio or train/serve diverges. Centralizing schema + topology + envelope math means the JS synth implements a *specification document* generated from `spec.py`, and the two can be validated against each other later (cross-engine audio diff is a Phase 5 acceptance test, not a Phase 6 one). `[CITED: synth-independence-decision.md §"Open conflicts" #1; ROADMAP Phase 5 cross-phase note]`

## Manifest Schema (per-pair `call_fm.json`)

**Location:** `data/pairs/NNN/call_fm.json` — sits beside `call.mid`/`response.mid`. `call.wav` becomes a **derived artifact** (rendered, gitignore-able) rather than a hand-authored input. `[ASSUMED]` — exact filename is Claude's discretion; `call_fm.json` chosen to avoid collision with `apollo/eval/render_manifest.py` (a *run* manifest for M4L eval — entirely different purpose; do not conflate).

**Proposed shape (small, hand-authorable, versioned):**
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

**Field semantics & ranges** (Claude's discretion; proposal):
| Field | Type | Range | Default | Notes |
|-------|------|-------|---------|-------|
| `spec_version` | string | — | `SPEC_VERSION` | Must match a version `spec.py` understands; mismatch → `IngestError`. |
| `algorithm` | int | `0..len(Algorithm)-1` | `0` | Index into the fixed topology set. |
| `operators` | array len **exactly 3** | — | — | One entry per operator; reject ≠3 (fail-loud). |
| `operators[].ratio` | float | `0.5..12` | `1.0` | FM frequency ratio (spike used 0.5–12). |
| `operators[].level` | float | `0..1` | varies | Modulation index/output level (mod index = `level * freq` style as in spike). |
| `operators[].attack/decay/release` | float (s) | `0..2` | small | ADSR; clamp to keep within gesture window. |
| `operators[].sustain` | float | `0..1` | — | ADSR sustain. |
| `gain` | float | `0..1` | `0.5` | Pre-normalization output gain. |

**Versioning:** every manifest carries `spec_version`. `manifest.py` rejects unknown versions (forward-compat guard so an old corpus can't silently re-render under a changed spec). The vocab-extensibility ethos from the project (reserve room without invalidating checkpoints) applies here: adding a 4th operator / new algorithm later bumps `SPEC_VERSION` and is handled explicitly. `[CITED: CLAUDE.md "extensible by design"]`

## 3-Op Faust Patch (extension of the proven 2-op spike)

The spike's 2-op patch (`car = osc(freq + mod); mod = osc(freq*ratio)*index*freq`) generalizes to 3 ops. **Recommend a small fixed algorithm set of 3 topologies, not a routing matrix** (decision rationale §2: keep conditioning low-dimensional for a small mel encoder).

Proposed `Algorithm` set (op3 → op2 → op1 = carrier; numbering DX-style):
- **Alg 0 — Stack (3→2→1):** chained modulation, one carrier. Brightest/clangorous range.
- **Alg 1 — Parallel mods (2+3 → 1):** two modulators sum into one carrier. Richer but controllable spectrum.
- **Alg 2 — Carrier pair (3→1, 2 as independent carrier):** two carriers, additive output. Fuller/organ-like.

Each is a distinct Faust `process` expression selected at DSP-string-generation time (the algorithm index picks which template `dsp_string()` emits). This keeps the compiled DSP simple and deterministic per manifest.

**Per-operator Faust params & the integer-index landmine:**
- The spike confirmed: under `num_voices`, params live at `/Polyphonic/Voices/dawdreamer/<name>` and **must be set by integer index**, not path. `freq`/`gain`/`gate` are owned by the MIDI layer and are NOT settable. `[CITED: spike-findings synth-independent-rendering.md "Landmines"]`
- **Action:** after `set_dsp_string`, call `synth.get_parameters_description()` once and build a name→index map; have `render.py` set each operator's `ratio`/`level`/ADSR by that resolved index. Do **not** hardcode indices (the spike hardcoded `0`/`1` for a 2-knob patch; a 3-op patch has many more and the ordering is Faust-determined). `PARAM_INDEX` in `spec.py` should be *derived at runtime* from the description, not a static literal.
- ADSR: spike used a single `en.adsr(...)` on the carrier. For 3-op, give **each operator its own envelope** (per-op ADSR is what makes FM expressive and what Operator-style synths do); expose all four ADSR params per op as Faust sliders.

**Polyphony:** keep `num_voices = 8` (spike value) so overlapping note releases don't cut. The corpus is monophonic (`load_notes` enforces it) but release tails of consecutive notes overlap, so voices > 1 is still needed.

## MIDI → Render Path

**Reuse `apollo/ingest/midi.py::load_notes`** rather than raw `pretty_midi`:
- It already enforces the corpus invariants this phase depends on — single instrument, monophony (`MONOPHONIC_EPS=1e-3`), non-empty, 120 BPM ±2 (`TEMPO_TOLERANCE_BPM`), DoS cap (`MAX_NOTES_PER_PAIR=1000`) — and raises `IngestError(pair_path, reason)` on violation. `[VERIFIED: apollo/ingest/midi.py]`
- It returns `Note(pitch, velocity, start, end)` in seconds, start-sorted. The render loop maps each to `synth.add_midi_note(pitch, velocity, start, dur=end-start)`. `[VERIFIED: spike render_fm.py uses exactly this 4-tuple]`

**Velocity → gain mapping:** DawDreamer's MIDI layer maps velocity→`gain` internally (the spike passed raw `velocity` 80–110 and got audible dynamics). Pass `note.velocity` straight through; do **not** double-apply a manifest `gain` to velocity — `gain` is a patch-level output trim, velocity is per-note. `[CITED: spike 001 — velocities 80–110 passed directly]`

**Render duration derivation:** spike hardcoded `DUR=1.5`. For the corpus, derive `dur = max(note.end for note) + tail`, where `tail` covers the longest operator `release` so the envelope isn't cut mid-decay. Then the `(96,128)` mel pad/truncate (96 frames ≈ 96*512/22050 ≈ 2.23 s) absorbs the rest — `MelExtractor` already pads short / truncates long, so over-rendering slightly is safe and under-rendering (clipping the tail) is the real risk. Recommend `tail = max_release + 0.1 s`. `[VERIFIED: MelExtractor._fix_frames pads to 96 frames]`

**120 BPM convention:** note timing arrives already in **seconds** from `load_notes`, so the renderer is tempo-agnostic at render time — it just places notes at their second offsets. The 120 BPM ±2 guard is enforced upstream in `load_notes`; the renderer doesn't re-check it. At inference, `generate.py` already reads BPM via `pretty_midi.estimate_tempo()` and passes it to `load_notes` — same path. `[VERIFIED: generate.py step 2; midi.py]`

## Determinism & Normalization

**Determinism — what guarantees bit-identical renders** (spike 001 confirmed `np.array_equal` true on re-render `[CITED: spike 001]`):
- Fixed `SR` and `BLOCK` (spike: 44100/512). Put both in `spec.py` constants so every render path uses identical engine config.
- No RNG in the Faust patch (pure oscillators + ADSR; no `no.noise`, no random init).
- Same render length for a given manifest (derive `dur` deterministically from notes + spec, not wall-clock).
- Fresh `RenderEngine` per render is fine and deterministic; the spike re-rendered into a new engine and got identical bytes.
- **Acceptance test:** re-render same manifest+MIDI, assert `np.array_equal` (spike pattern). No audio fixture needed — render twice in-process.

**Normalization / headroom** (spike saw peaks 1.13–1.19; `soundfile` PCM clips to [-1,1] `[CITED: spike-findings "Output clips"]`):
- Apply **peak normalization with headroom**: `audio = audio / max(peak, 1e-9) * target_peak` where `target_peak ≈ 0.89` (≈ −1 dBFS). This is deterministic (a scalar derived from the signal), prevents clipping, and **preserves spectral shape** — peak normalization is a pure gain change, so it does not alter the mel *timbre* signal (only overall log-mel offset, which the encoder handles; spike 002 showed brightness differences survive). Do **not** use RMS/loudness normalization or a compressor/limiter — those are non-linear or content-dependent and would distort the timbre conditioning the model learns. `[CITED: spike 002 timbre-discriminable; ASSUMED on exact target_peak — Claude's discretion within "headroom that doesn't clip"]`
- Normalize **before** `soundfile.write`, after mono/stereo handling. Spike wrote stereo (`<: _,_`); `MelExtractor` mono-mixes anyway, so either render mono (simpler, smaller) or keep stereo — mono recommended to halve file size and remove any L/R asymmetry as a determinism variable.

**Train/serve consistency pitfall:** the corpus render and the `generate.py` inference render **must call the identical `render.py` function with identical normalization**. If normalization differs (e.g. corpus normalizes, inference doesn't), the mel distribution shifts between train and serve — exactly the domain gap DATA-06 forbids. Enforce by having one `render_call_wav(manifest_path, mid_path) -> wav_path | np.ndarray` used by both surfaces.

## Train/Serve Parity Wiring (generate.py)

Currently `generate.py` takes `call_wav` as a **file argument** and requires it to exist (step "call.wav not found → return 1"). `[VERIFIED: generate.py lines 122–149]` To close the train/serve gap:

- **Option A (recommended):** Replace the `call_wav` positional with a derivation — `generate.py` reads `data/pairs/NNN/call_fm.json` (next to `call.mid`), renders `call.wav` via `apollo.synth.render.render_call_wav`, then feeds the result to `MelExtractor`. This guarantees inference uses the identical engine + manifest the corpus used.
- **Option B (transitional):** Keep an optional `--call-wav` override but default to rendering from the manifest, so existing callers don't break mid-migration.
- Either way, the mel step (`mx(...)` → `(1,1,96,128)`) is unchanged. The only change is *where the wav comes from*. `[VERIFIED: generate.py step 4 mel extraction is engine-agnostic]`

**Pitfall:** `generate.py` reads BPM via `estimate_tempo()` and passes it to `load_notes`; ensure the render path uses the **same** `load_notes(call_bpm)` call (don't parse the MIDI twice with different tempo assumptions). Render and tokenize from one parsed `call_notes` list.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| FM oscillator + envelope DSP | Custom numpy sine/PM synth | Faust `os.osc` + `en.adsr` via dawdreamer | Spike-proven, anti-aliased, deterministic; hand-rolled PM aliases and drifts from the spec. |
| MIDI parsing + monophony/tempo guards | New parser in `render.py` | `apollo/ingest/midi.py::load_notes` | Validation + DoS caps already exist and are tested. |
| Mel extraction / contract | Any mel code in the synth | `apollo/ingest/audio.py::MelExtractor` (unchanged) | COND-01 is frozen; spike 002 proved drop-in. |
| Param-path addressing under polyphony | Hardcoded indices or path strings | `get_parameters_description()` → name→index map | Path strings RuntimeError under `num_voices`; hardcoded indices break when the patch grows. |
| Clip prevention | Compressor/limiter | Scalar peak normalization with headroom | Non-linear stages distort the timbre conditioning signal. |

**Key insight:** Phase 6 is mostly *integration of already-validated pieces*. The genuinely new code is the 3-op DSP-string generator, the manifest schema/validator, and the parity wiring. Everything else is reuse.

## Common Pitfalls

### Pitfall 1: Hardcoding Faust param indices
**What goes wrong:** Spike used `set_parameter(0, index); set_parameter(1, ratio)` for a 2-knob patch. A 3-op patch has ~12+ settable params; Faust assigns indices by declaration order, which changes as you edit the DSP.
**How to avoid:** Resolve indices at runtime from `get_parameters_description()` into a name→index dict; set by resolved index. `[CITED: spike landmines]`
**Warning sign:** `RuntimeError` from `set_parameter`, or a param silently not taking effect (wrong index).

### Pitfall 2: Render length cuts the release tail
**What goes wrong:** `render(last_note_end)` truncates envelope releases → clicks/altered spectrum → shifted mel.
**How to avoid:** `dur = last_note_end + max_release + 0.1`. MelExtractor pads short clips, so erring long is safe.

### Pitfall 3: Normalization mismatch between corpus and inference
**What goes wrong:** Corpus renders normalized, inference renders raw (or vice-versa) → mel distribution shift → train/serve domain gap (the exact thing DATA-06 forbids).
**How to avoid:** One `render_call_wav` function used by both `render_corpus` and `generate.py`.

### Pitfall 4: Naming collision with `eval/render_manifest.py`
**What goes wrong:** `apollo/eval/render_manifest.py` already exists — it's the **M4L eval run manifest** (one entry per held-out pair), unrelated to FM params. Reusing the name "manifest" loosely confuses readers. `[VERIFIED: apollo/eval/render_manifest.py]`
**How to avoid:** Name the per-pair file `call_fm.json` and the module `apollo/synth/manifest.py` (namespaced under `synth`, distinct from `eval`). Document the distinction in CORPUS-CONVENTIONS.

### Pitfall 5: Treating `call.wav` as a hand-authored input
**What goes wrong:** Conventions/tests still expect `call.wav` to exist as authored. Post-phase it's a *derived* artifact.
**How to avoid:** Update CORPUS-CONVENTIONS to "author `call.mid`, `call_fm.json`, `response.mid`; `call.wav` is rendered." Decide whether rendered wavs are committed or gitignored (recommend gitignore — they're reproducible from manifest+MIDI, which is the whole point of determinism).

## Security Domain

`security_enforcement` enabled. The renderer parses MIDI + JSON and writes WAV — same threat surface class as `MelExtractor` (which enforces T-01-07 size cap, T-01-08 duration cap).

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | yes | `manifest.py` validates JSON shape + numeric ranges; reject unknown `spec_version`; require exactly 3 operators; clamp/abort out-of-range params via `IngestError`. |
| V5 (resource caps) | yes | Cap render duration (mirror `MAX_WAV_SECONDS=30`); MIDI note count cap already enforced by `load_notes` (`MAX_NOTES_PER_PAIR=1000`). Cap derived `dur` so a malicious manifest can't request a huge render. |
| V6 Cryptography | no | No crypto in scope. |

### Threat Patterns
| Pattern | STRIDE | Mitigation |
|---------|--------|-----------|
| Oversized/long render via crafted manifest (CPU/RAM DoS) | DoS | Cap `dur` (e.g. ≤ 30 s, matching MelExtractor); reject manifests that would exceed it. |
| Malformed JSON / wrong types / NaN-Inf params | Tampering | `manifest.py` strict parse: type-check, finite-check, range-check each field; `IngestError` on any violation (fail-loud, names the pair). |
| Out-of-range FM params producing pathological output | Tampering | Enforce documented ranges (ratio 0.5–12, level/gain 0–1, ADSR 0–2 s) at load time. |
| Faust DSP injection via manifest | Tampering | **Manifest values are numbers/ints only** — never interpolate user strings into the DSP source. `dsp_string()` builds from the fixed templates + numeric params; no string field reaches Faust. |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| dawdreamer | Render engine | ✗ (not yet a project dep) | target `==0.8.3` | none — phase blocked without it; spike used isolated venv. Add to pyproject. |
| Python 3.11 | dawdreamer wheel | ✓ | project `requires-python>=3.11` | none (wheel is 3.11+ arm64 macOS). |
| Faust toolchain | DSP compile | ✓ (bundled in dawdreamer) | — | not needed separately. |
| soundfile / numpy / pretty_midi / torch | I/O, mel, MIDI | ✓ | already deps | — |

**Note:** spike installed dawdreamer in an **isolated** venv (heavy wheel) for the render step, and used the **project** venv (with torch) to import `apollo` for the mel check. Since this phase puts the renderer *inside* `apollo` and wires it into `generate.py`, dawdreamer must coexist with torch in the **project** venv. `[CITED: spike-findings "Constraints"]` This was not directly validated in a single combined venv — flag as a low-risk install check at execution time (both are large wheels; verify they coexist on arm64/Py3.11). `[ASSUMED]`

## Test Strategy (no shipped audio fixtures)

Nyquist validation is **disabled** for this project (`workflow.nyquist_validation: false`), so a full Validation Architecture section is omitted. Recommended tests (all render in-process; **no committed wav fixtures**):

- **Determinism:** render same manifest+MIDI twice → `np.array_equal` (spike 001 pattern).
- **Mel contract:** rendered wav → `MelExtractor` → assert shape `(96,128)`, float32 (spike 002 pattern, in-process temp wav).
- **Timbre discriminability (smoke):** two contrasting manifests → mels differ (`cos < 0.999`, `L2 > 1`) (spike 002 pattern).
- **No clipping:** `max(abs(audio)) <= 1.0` after normalization.
- **Manifest validation:** malformed/out-of-range/wrong-op-count manifests → `IngestError`.
- **Parity:** corpus render and `generate.py`'s render produce identical audio for the same pair (call one shared function).
- **Skip-if-unavailable:** guard dawdreamer-dependent tests with a skip if the wheel isn't importable, so CI on non-arm64 doesn't hard-fail (mirrors spike's platform constraint). `[ASSUMED — CI platform unknown]`

Existing `tests/test_render_manifest.py` is for the **eval** manifest — do not extend it; add `tests/test_synth_render.py`.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Manifest filename `call_fm.json` at `data/pairs/NNN/` | Manifest Schema | Low — naming is Claude's discretion; just pick one and document it. |
| A2 | `target_peak ≈ 0.89` (−1 dBFS) headroom | Determinism & Normalization | Low — any value < 1.0 prevents clipping; exact value is discretionary, just keep it constant across train/serve. |
| A3 | 3 fixed algorithm topologies (stack / parallel-mod / carrier-pair) is the right minimal set | 3-Op Faust Patch | Medium — if authors need other routings, add to the set (bump SPEC_VERSION). Confirm the set covers intended timbres before authoring 30 pairs. |
| A4 | dawdreamer coexists with torch in one project venv on arm64/Py3.11 | Environment Availability | Medium — spike used separate venvs; verify combined install early in the phase before building on it. |
| A5 | Rendered `call.wav` should be gitignored (derived, reproducible) | Common Pitfalls #5 | Low — alternatively commit them; either is defensible. Determinism makes gitignore safe. |
| A6 | CI may run on non-arm64 → dawdreamer tests need skip guards | Test Strategy | Low — only matters if CI exists on Linux/x86; local dev is arm64. |

## Open Questions

1. **Commit rendered wavs or gitignore?**
   - Known: determinism makes them reproducible from `call_fm.json` + `call.mid`.
   - Unclear: whether DATA-05's "≥30 pairs" gate counts authored manifests or rendered wavs.
   - Recommendation: gitignore wavs, count manifests; render is a build step (`render_corpus`).

2. **Does the 3-algorithm set cover the timbres the user wants to author?**
   - Known: spike proved timbre varies with ratio/index; 3 topologies span stack→parallel→dual-carrier.
   - Unclear: whether the user's intended corpus needs a routing not in the set.
   - Recommendation: confirm with the user during discuss/plan before authoring begins (A3).

3. **Single combined venv (dawdreamer + torch) install health on arm64/Py3.11?**
   - Recommendation: first execution task installs both and imports both, before any feature work (A4).

## Sources

### Primary (HIGH confidence)
- `.claude/skills/spike-findings-apollo/references/synth-independent-rendering.md` — validated render+mel code, landmines (poly index, clipping, no `__version__`), constraints.
- `.planning/spikes/001-dawdreamer-fm-render/render_fm.py` — runnable 2-op render skeleton, determinism check, peak/rms output.
- `.planning/spikes/002-fm-mel-conditioning/mel_check.py` — mel contract + timbre-discriminability check against production `MelExtractor`.
- `apollo/ingest/audio.py` — COND-01 `(96,128)` contract, security caps T-01-07/08.
- `apollo/ingest/midi.py` — `load_notes` monophony/tempo/DoS guards.
- `apollo/scripts/generate.py` — inference entrypoint; current `call_wav` file argument to be replaced by render.
- `.planning/notes/synth-independence-decision.md` — locked decision, rationale, Phase 5 reconciliation.
- `.planning/phases/06-.../06-CONTEXT.md` — locked decisions + discretion.
- `pyproject.toml` — current deps (dawdreamer absent).

### Secondary (MEDIUM confidence)
- [dawdreamer · PyPI](https://pypi.org/project/dawdreamer/) — confirms `0.8.3` is latest; arm64/Py3.11 wheels.
- [DBraun/DawDreamer (GitHub)](https://github.com/DBraun/DawDreamer) — `render(seconds)`, `add_midi_note`, `set_parameter`, block-size 512 examples; Python 3.11+ support.

## Metadata
**Confidence breakdown:**
- Standard stack: HIGH — spike-validated, version verified on PyPI.
- Architecture / parity wiring: HIGH — derived from read of actual `generate.py` + ingest code.
- 3-op DSP / algorithm set: MEDIUM — extension of proven 2-op; specific topology set is a recommendation (A3).
- Determinism: HIGH — spike empirically confirmed `np.array_equal`.
- Normalization detail: MEDIUM — approach sound; exact target_peak discretionary (A2).

**Research date:** 2026-06-02
**Valid until:** ~2026-09-02 (dawdreamer release cadence is slow; 0.8.3 stable).

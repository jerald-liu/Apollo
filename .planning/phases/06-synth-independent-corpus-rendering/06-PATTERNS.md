# Phase 6: Synth-Independent Corpus Rendering - Pattern Map

**Mapped:** 2026-06-02
**Files analyzed:** 11 (4 new modules, 1 new CLI, 1 new test, 1 module edit, 1 `__init__` edit, 3 doc/config edits)
**Analogs found:** 9 / 9 code-bearing files (doc/config files map to in-repo conventions)

This phase is overwhelmingly *integration of validated pieces* (RESEARCH §"Don't Hand-Roll"). Nearly every new file has a strong in-repo analog: the renderer mirrors `apollo/ingest/audio.py`, MIDI parsing reuses `apollo/ingest/midi.py::load_notes` verbatim, validation mirrors the `IngestError` fail-loud style, the spec module mirrors the frozen-dataclass `Vocab`, the CLI mirrors `ingest_corpus.py`, and tests mirror `test_mel_extractor.py`.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `apollo/synth/__init__.py` | package init | — | `apollo/ingest/__init__.py` | exact |
| `apollo/synth/spec.py` | config / source-of-truth schema | transform (params → DSP string) | `apollo/tokenizer/vocab.py` (frozen-dataclass SoT) + `apollo/ingest/audio.py` (class-level config consts) | role-match |
| `apollo/synth/manifest.py` | model / validator | file-I/O (JSON load + validate) | `apollo/ingest/midi.py::load_notes` (load+validate+fail-loud) | role-match |
| `apollo/synth/render.py` | service / feature extractor | transform (manifest+notes → audio array) | `apollo/ingest/audio.py::MelExtractor` (callable, caps, IngestError) | exact (role+flow) |
| `apollo/scripts/render_corpus.py` | CLI entrypoint | batch | `apollo/scripts/ingest_corpus.py` | exact |
| `apollo/scripts/generate.py` (edit) | CLI entrypoint | request-response | itself (current `call_wav` arg path) | self |
| `tests/test_synth_render.py` | test | transform | `tests/test_mel_extractor.py` | exact |
| `pyproject.toml` (edit) | config | — | itself (`[project].dependencies`) | self |
| `data/pairs/CORPUS-CONVENTIONS.md` (edit) | doc | — | itself | self |
| `.planning/REQUIREMENTS.md` (edit) | doc | — | itself (DATA-06 already added) | self |

## Pattern Assignments

### `apollo/synth/__init__.py` (package init)

**Analog:** `apollo/ingest/__init__.py` (whole file)

Mirror the docstring-then-re-export-then-`__all__` shape. The ingest init lists the public surface in the module docstring (lines 1–15), imports each symbol from its submodule (lines 17–23), and declares `__all__` (lines 25–38). Replicate for the synth package: export `FmParams`, `Algorithm`, `SPEC_VERSION`, `dsp_string` (from `.spec`); `load_manifest` (from `.manifest`); `render`, `render_call_wav` (from `.render`).

```python
"""Apollo synth package — headless FM renderer (DawDreamer + Faust).

Public surface:
    - FmParams         (frozen dataclass: full 3-op FM parameter set)
    - Algorithm        (IntEnum: fixed operator-routing topologies)
    - SPEC_VERSION     (str constant; written into every manifest)
    - dsp_string       (FmParams -> Faust DSP source; only place a patch is built)
    - load_manifest    (path, pair_path -> FmParams, IngestError on bad input)
    - render           (params, notes -> np.ndarray, deterministic + normalized)
    - render_call_wav  (manifest_path, mid_path -> wav path | np.ndarray)
"""
from .spec import SPEC_VERSION, Algorithm, FmParams, dsp_string
from .manifest import load_manifest
from .render import render, render_call_wav

__all__ = [...]
```

---

### `apollo/synth/spec.py` (config / single source of truth, transform)

**Analogs:** `apollo/tokenizer/vocab.py` (frozen-dataclass-as-contract + extensibility docstring) and `apollo/ingest/audio.py` (class-level numeric config constants).

**Frozen dataclass + "do not mutate without version bump" docstring** — `vocab.py` lines 1–23, 27–49. This is the exact pattern for a versioned source-of-truth. Note the docstring explicitly states the contract ("the single source of truth"), enumerates the layout, and warns that mutation invalidates checkpoints — `spec.py` should do the same for `SPEC_VERSION` (RESEARCH §"Versioning"; CONTEXT "extensible by design"):

```python
"""Frozen FM spec — the single source of truth Phase 5's browser synth mirrors.

Owns three things: the FM parameter schema (ranges/defaults), the algorithm set
(fixed 3-op routing topologies), and envelope semantics. `dsp_string()` is the
ONLY place a Faust patch is constructed.

Do not mutate field ranges or algorithm semantics without bumping SPEC_VERSION —
any change can re-render an already-authored corpus differently (breaks determinism
reproducibility). New ops / algorithms bump the version and are handled explicitly.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import IntEnum

SPEC_VERSION = "1.0"

class Algorithm(IntEnum):
    STACK = 0          # 3→2→1 chained modulation
    PARALLEL_MODS = 1  # (2+3)→1
    CARRIER_PAIR = 2   # 3→1, 2 independent carrier

@dataclass(frozen=True)
class FmParams:
    ...
```

**Class-level fixed config constants** — mirror `MelExtractor` lines 35–45 (`TARGET_SR`, `N_FFT`, etc., with grouping comments citing decisions). Put determinism-critical engine config here so every render path shares it (RESEARCH §"Determinism"):

```python
    # ---- Engine config (determinism-critical; spike 001) ----
    SR = 44100
    BLOCK = 512
    NUM_VOICES = 8
    TARGET_PEAK = 0.89   # ~ -1 dBFS headroom (A2)
```

**Faust DSP-string generation (the transform):** the proven 2-op template lives in `.claude/skills/spike-findings-apollo/references/synth-independent-rendering.md` lines 14–38 (`FM_DSP` string with `os.osc`/`en.adsr`). `dsp_string(p)` selects one of 3 templates by `p.algorithm` and substitutes **numeric params only** — never interpolate manifest strings (RESEARCH §"Security Domain" — Faust DSP injection). The spike DSP exposes `freq`/`gain`/`gate` (MIDI-owned, NOT settable) plus the settable `ratio`/`index` sliders; 3-op gives each operator its own `en.adsr(...)` + `ratio`/`level` slider.

---

### `apollo/synth/manifest.py` (validator, file-I/O)

**Analog:** `apollo/ingest/midi.py::load_notes` (whole file) — the load + validate + fail-loud-with-pair-path pattern.

**Module-level cap/tolerance constants with decision-citing comments** — `midi.py` lines 29–41 (`MAX_NOTES_PER_PAIR`, `MONOPHONIC_EPS`, `TEMPO_TOLERANCE_BPM`). Replicate for manifest validation bounds (RESEARCH §"Security Domain" ranges: ratio 0.5–12, level/gain 0–1, ADSR 0–2 s, exactly 3 ops, `MAX_RENDER_SECONDS` mirroring `MelExtractor.MAX_WAV_SECONDS=30`):

```python
MAX_RENDER_SECONDS = 30.0   # mirror MelExtractor.MAX_WAV_SECONDS (T-01-08 class)
N_OPERATORS = 3             # reject != 3 (fail-loud)
RATIO_MIN, RATIO_MAX = 0.5, 12.0
```

**Parse-then-validate-then-raise structure** — `load_notes` lines 58–110: wrap the parse in try/except → `IngestError(pair_path, ...)`, then a sequence of guard checks each raising `IngestError` with a message that names the file. Replicate exactly for `load_manifest(path, pair_path) -> FmParams`:

```python
try:
    raw = json.loads(Path(path).read_text())
except Exception as e:
    raise IngestError(pair_path, f"failed to parse {path}: {e}")

if raw.get("spec_version") != SPEC_VERSION:
    raise IngestError(pair_path, f"manifest spec_version {raw.get('spec_version')!r} "
                                 f"!= supported {SPEC_VERSION!r}")
ops = raw.get("operators", [])
if len(ops) != N_OPERATORS:
    raise IngestError(pair_path, f"expected exactly {N_OPERATORS} operators, got {len(ops)}")
# per-field type/finite/range checks, each → IngestError(pair_path, ...)
```

Note: `audio.py` lines 153–157 (`load_artifact`) shows the parallel "version mismatch → raise" guard for the SoT-version check.

---

### `apollo/synth/render.py` (service / feature extractor, transform)

**Analog:** `apollo/ingest/audio.py::MelExtractor` (whole file) — same role (deterministic array producer feeding a frozen downstream contract), same flow, same IngestError discipline, same security-cap posture.

**Module docstring citing the contract + threat mitigations** — `audio.py` lines 1–12. Render's docstring should state: deterministic (spike 001 `np.array_equal`), feeds `MelExtractor` `(96,128)` unchanged, normalization/headroom before write, render-duration cap.

**Reuse `load_notes`, do NOT re-parse MIDI** (RESEARCH §"MIDI → Render Path", §"Don't Hand-Roll"). Import exactly as `audio.py`/`generate.py` do:

```python
from apollo.ingest.errors import IngestError
from apollo.ingest.midi import load_notes
from apollo.synth.spec import FmParams, dsp_string, SR, BLOCK, NUM_VOICES, TARGET_PEAK
```

**Core render loop** — the proven skeleton is in the spike reference lines 28–38: `RenderEngine(SR,BLOCK)` → `make_faust_processor` → `set_dsp_string(dsp_string(params))` → `num_voices = NUM_VOICES` → resolve param indices → `add_midi_note(pitch, velocity, start, dur)` per `Note` → `load_graph` → `render(dur)` → `get_audio()`. Map each `load_notes` `Note(pitch, velocity, start, end)` to `add_midi_note(n.pitch, n.velocity, n.start, n.end - n.start)`.

**Landmines (MUST honor; spike reference lines 57–69 + RESEARCH Pitfall 1):**
- Resolve param indices at runtime from `synth.get_parameters_description()` into a name→index dict; `set_parameter(<int index>, value)`. Never path strings, never hardcoded indices.
- Filter the benign `undefined symbol : effect` warning.
- No `dawdreamer.__version__`.

**Security caps mirror `MelExtractor`** — `audio.py` lines 43–45, 83–89. Cap derived render duration before rendering:

```python
dur = max(n.end for n in notes) + max_release + 0.1   # RESEARCH §"Render duration"
if dur > MAX_RENDER_SECONDS:
    raise IngestError(pair_path, f"render duration {dur:.2f}s exceeds cap ({MAX_RENDER_SECONDS}s)")
```

**Normalization (scalar peak, deterministic; RESEARCH §"Normalization"):**
```python
peak = float(np.max(np.abs(audio)))
audio = audio / max(peak, 1e-9) * TARGET_PEAK   # ~-1 dBFS; pure gain, preserves timbre
```
Do NOT use RMS/loudness/compressor — non-linear stages distort the conditioning signal.

**One shared parity function** — expose `render_call_wav(manifest_path, mid_path, *, call_bpm) -> np.ndarray | wav_path` and have BOTH `render_corpus.py` and `generate.py` call it, so corpus and inference renders are bit-identical (RESEARCH Pitfall 3, §"Train/Serve Parity").

---

### `apollo/scripts/render_corpus.py` (CLI entrypoint, batch)

**Analog:** `apollo/scripts/ingest_corpus.py` (whole file) — exact structural match for an argparse CLI that iterates `data/pairs/` and maps `IngestError` to exit code 1.

Replicate verbatim: the module docstring's **exit-code table** (lines 1–13: 0 success, 1 `IngestError`, 2 other), the `main(argv=None) -> int` signature, `argparse` with a `pairs_root` positional + `--output`/`--tempo-bpm`-style flags (use `--tempo-bpm` default 120.0 to pass through to `load_notes`), and the try/except mapping:

```python
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Render call.wav for every pair from its FM manifest.")
    parser.add_argument("pairs_root", help="Path to the data/pairs/ directory")
    parser.add_argument("--tempo-bpm", type=float, default=120.0, ...)
    args = parser.parse_args(argv)
    try:
        ...  # discover_pairs(root); per pair render_call_wav(...) -> soundfile.write
        print(f"OK: rendered {n} call.wav -> ...")
        return 0
    except IngestError as e:
        print(f"RENDER FAILED: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"UNEXPECTED ERROR: {e!r}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    sys.exit(main())
```

Use `apollo.ingest.discover_pairs` for pair enumeration (already public per `ingest/__init__.py`).

---

### `apollo/scripts/generate.py` (CLI edit, request-response)

**Analog:** itself — the existing `call_wav` path at lines 116–149 and 162–176.

**The change (RESEARCH §"Train/Serve Parity Wiring", Option A recommended):** replace the `call_wav` positional + "call.wav not found → return 1" guard (lines 122, 147–149) with on-the-fly rendering from `data/pairs/NNN/call_fm.json`. Keep everything else unchanged — the mel step at lines 174–176 (`mx(...)` → `(1,1,96,128)`) is engine-agnostic.

Critical reuse-of-one-parse pitfall (RESEARCH §"Train/Serve Parity Wiring" pitfall): `generate.py` already computes `call_bpm` via `estimate_tempo()` (line 162) and parses `call_notes = load_notes(..., tempo_bpm=call_bpm)` (lines 166–168). Pass that **same** `call_bpm` into `render_call_wav` so the render and the tokenize paths share one tempo assumption — do not parse the MIDI twice with different tempo. New import:

```python
from apollo.synth.render import render_call_wav
```

Then between current step 3 and step 4, render the wav (instead of reading `args.call_wav`), feed the array/temp-path to `MelExtractor`. Option B (transitional `--call-wav` override defaulting to render) is acceptable if mid-migration callers exist.

---

### `tests/test_synth_render.py` (test, transform)

**Analog:** `tests/test_mel_extractor.py` (whole file). Do NOT extend `tests/test_render_manifest.py` — that is the *eval* manifest (RESEARCH Pitfall 4).

Mirror its conventions: `from __future__ import annotations`, `import pytest`, helper that synthesizes inputs in `tmp_path` (the `_write_silence` pattern at lines 20–24 — here synthesize a tiny `call.mid` + a `call_fm.json`), one assertion per test, and `pytest.raises(IngestError, match=...)` for the failure cases (lines 74–86).

Tests to write (RESEARCH §"Test Strategy"):
- **Determinism:** render same manifest+MIDI twice → `np.array_equal` (spike 001).
- **Mel contract:** rendered wav → `MelExtractor` → `assert out.shape == (96, 128)` and `out.dtype == torch.float32` (mirror lines 27–42).
- **Timbre discriminability (smoke):** two contrasting manifests → mels differ (`cos < 0.999`, `L2 > 1`).
- **No clipping:** `np.max(np.abs(audio)) <= 1.0` after normalization.
- **Manifest validation:** malformed / out-of-range / wrong-op-count / bad `spec_version` → `IngestError` (mirror the `pytest.raises(IngestError, match=...)` style).
- **Parity:** corpus render and `generate.py`'s render produce identical audio for the same pair (call the one shared `render_call_wav`).
- **Skip-if-unavailable:** guard dawdreamer-dependent tests with `pytest.importorskip("dawdreamer")` so non-arm64 CI doesn't hard-fail (A6).

---

### `pyproject.toml` (config edit)

**Analog:** itself, lines 10–16 (`[project].dependencies`). Add one pinned dep (RESEARCH §"Standard Stack" — pin exactly, native wheel, determinism reproducibility):

```toml
    "dawdreamer==0.8.3",
```

Early-phase install-health check (A4): verify dawdreamer coexists with torch in the project venv on arm64/Py3.11 before building features — the spike used separate venvs.

---

### `data/pairs/CORPUS-CONVENTIONS.md` (doc edit)

**Analog:** itself. Edits required (CONTEXT §"Docs / requirements to reconcile", RESEARCH Pitfall 5):
- "Per-pair file layout (DATA-02)": `call.wav` is no longer a hand-authored "Manual Ableton bounce" — it becomes a *derived* artifact rendered from `call_fm.json`. Add `call_fm.json` as the new authored input.
- "Operator preset / D-02" row: timbre is now a hand-authored FM-param manifest, not an Ableton Operator preset.
- "Authoring workflow (Ableton)" section (steps 1–7, the bounce step #4): replace with the FM-manifest workflow — author `call.mid`, `call_fm.json`, `response.mid`; `call.wav` is rendered by `python -m apollo.scripts.render_corpus`.
- Document `call_fm.json` vs `eval/render_manifest.py` distinction (RESEARCH Pitfall 4) and the gitignore-vs-commit decision for rendered wavs (Open Question 1; recommend gitignore + count manifests).

---

### `.planning/REQUIREMENTS.md` (doc edit)

**Analog:** itself. DATA-06 already exists (line 15). Amend DATA-01 (line 10) and DATA-02 (line 11) wording — they still say "author in Ableton" / "manual Ableton bounce" — to note they are superseded by DATA-06's FM-manifest premise (CONTEXT, RESEARCH §"User Constraints"). Update the traceability table rows (lines 99–104) if status wording changes.

## Shared Patterns

### Fail-loud with pair path: `IngestError`
**Source:** `apollo/ingest/errors.py` lines 15–21 — `IngestError(pair_path, reason)` formats as `[{pair_path}] {reason}`.
**Apply to:** `apollo/synth/manifest.py` (all validation failures), `apollo/synth/render.py` (parse/cap failures). Reuse the existing class; do not define a new exception. Both the corpus CLI and tests rely on it (exit-code-1 mapping + `pytest.raises(IngestError, match=...)`).

```python
from apollo.ingest.errors import IngestError
raise IngestError(pair_path, f"<message naming the offending file/field>")
```

### CLI exit-code contract (0 / 1 / 2)
**Source:** `apollo/scripts/ingest_corpus.py` lines 1–13 (docstring table) + 43–55 (try/except).
**Apply to:** `apollo/scripts/render_corpus.py`. `IngestError` → 1, any other exception → 2, success → 0, `main(argv=None) -> int`, `sys.exit(main())` guard.

### Source-of-truth versioning + frozen dataclass
**Source:** `apollo/tokenizer/vocab.py` lines 1–23, 30–49 (frozen dataclass, "do not mutate without bumping version" docstring) and `apollo/ingest/artifact.py` lines 152–156 (version-mismatch → raise).
**Apply to:** `apollo/synth/spec.py` (`SPEC_VERSION`, `FmParams`, `Algorithm`) and `apollo/synth/manifest.py` (reject unknown `spec_version`).

### Security caps mirror MelExtractor
**Source:** `apollo/ingest/audio.py` lines 43–45 (`MAX_WAV_BYTES`, `MAX_WAV_SECONDS`), 83–89 (duration-cap raise).
**Apply to:** `apollo/synth/render.py` (`MAX_RENDER_SECONDS = 30.0`, cap derived `dur`) and `apollo/synth/manifest.py` (finite/range/op-count caps). MIDI note-count DoS cap is already enforced upstream by `load_notes` (`MAX_NOTES_PER_PAIR`), so do not re-implement it — just reuse `load_notes`.

### Reuse `load_notes` for MIDI (one validation path)
**Source:** `apollo/ingest/midi.py::load_notes` lines 44–120; used by `apollo/scripts/generate.py` lines 166–168 and `apollo/ingest/artifact.py` lines 91–96.
**Apply to:** `apollo/synth/render.py` and `apollo/scripts/generate.py` render hook. Returns `Note(pitch, velocity, start, end)` start-sorted with monophony/tempo/empty/DoS guards already enforced.

### Spike-validated render skeleton + landmines
**Source:** `.claude/skills/spike-findings-apollo/references/synth-independent-rendering.md` lines 14–38 (skeleton), 57–69 (landmines).
**Apply to:** `apollo/synth/render.py` and `apollo/synth/spec.py`. Integer-index params (not path strings), filter `undefined symbol : effect`, no `__version__`, normalization before write, `num_voices=8`.

## No Analog Found

None. Every code-bearing file has a strong in-repo analog. The only genuinely new logic with no direct analog is the **3-op Faust DSP-string templates** inside `spec.py::dsp_string` — but even that extends the proven 2-op spike template (spike reference lines 14–38), so it is a documented extension rather than greenfield. Doc/config files are self-edits.

## Metadata

**Analog search scope:** `apollo/ingest/`, `apollo/scripts/`, `apollo/tokenizer/`, `apollo/eval/`, `tests/`, `.claude/skills/spike-findings-apollo/`, `pyproject.toml`, `data/pairs/CORPUS-CONVENTIONS.md`, `.planning/REQUIREMENTS.md`
**Files scanned:** 39 python files + skill reference + 2 docs + pyproject
**Pattern extraction date:** 2026-06-02

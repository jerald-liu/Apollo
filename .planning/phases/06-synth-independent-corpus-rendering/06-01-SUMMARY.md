---
phase: 06-synth-independent-corpus-rendering
plan: 01
subsystem: synth
tags: [dawdreamer, faust, fm-synthesis, manifest, validation, determinism]

# Dependency graph
requires:
  - phase: 01-tokenizer-ingest
    provides: IngestError fail-loud pattern, frozen-dataclass-as-contract (vocab.py), class-level config consts (MelExtractor)
provides:
  - dawdreamer==0.8.3 pinned and verified coexisting with torch 2.12 in one project venv (A4 cleared)
  - apollo/synth/spec.py — FM single source of truth (SPEC_VERSION, 3-member Algorithm, frozen FmParams/OperatorParams, engine consts, numeric-only dsp_string)
  - apollo/synth/manifest.py — fail-loud per-pair manifest validator returning FmParams
  - apollo/synth package public surface
affects: [06-02 render path, 06-03 corpus/generate wiring, Phase 5 browser synth spec]

# Tech tracking
tech-stack:
  added: [dawdreamer==0.8.3]
  patterns:
    - "Versioned single-source-of-truth FM spec (frozen dataclass + SPEC_VERSION, mirrors vocab.py)"
    - "Numeric-only Faust DSP-string generation (no manifest string ever reaches DSP source)"
    - "Parse->validate->raise-IngestError manifest boundary (mirrors midi.py::load_notes)"

key-files:
  created:
    - apollo/synth/spec.py
    - apollo/synth/manifest.py
    - apollo/synth/__init__.py
  modified:
    - pyproject.toml

key-decisions:
  - "A4 CLEARED: dawdreamer 0.8.3 + torch 2.12.0 import cleanly in one .venv on arm64/Py3.11 — no venv isolation needed for 06-02/06-03"
  - "Per-op slider naming scheme: op{i}_ratio, op{i}_level, op{i}_attack, op{i}_decay, op{i}_sustain, op{i}_release (i 1-based) — render.py resolves names->indices at runtime"
  - "Modulation depth convention: modulator deviates carrier freq by (op_output * level * freq); carriers scaled by level then master gain"
  - "Mono output (single _) — halves file size, removes L/R asymmetry as a determinism variable"
  - "Manifest field ranges mirror Faust hslider ranges exactly so a manifest can never request a value the DSP would silently clamp"

patterns-established:
  - "FM spec is the contract Phase 5's browser synth mirrors; mutate only with a SPEC_VERSION bump"
  - "dsp_string takes only FmParams (numeric) — Faust-injection mitigation T-06-03 enforced at the type boundary"

requirements-completed: [DATA-06]

# Metrics
duration: ~12min
completed: 2026-06-02
---

# Phase 6 Plan 01: Synth Spec & Manifest Foundation Summary

**Owned 3-operator FM spec (SPEC_VERSION, 3 algorithms, per-op ADSR, numeric-only Faust dsp_string) plus a fail-loud per-pair manifest validator, with dawdreamer==0.8.3 verified coexisting with torch in one project venv.**

## Performance

- **Duration:** ~12 min
- **Tasks:** 3
- **Files modified:** 4 (3 created, 1 edited)

## Accomplishments
- **A4 risk gate cleared:** `import torch, dawdreamer` succeeds in the single project `.venv` on arm64/Py3.11; `dawdreamer.RenderEngine` present. No venv isolation needed — 06-02/06-03 can assume one interpreter.
- **spec.py** is the single source of truth: `SPEC_VERSION="1.0"`, `Algorithm(IntEnum)` with exactly 3 members (STACK/PARALLEL_MODS/CARRIER_PAIR), frozen `FmParams`/`OperatorParams`, engine constants (SR=44100, BLOCK=512, NUM_VOICES=8, TARGET_PEAK=0.89), and a numeric-only `dsp_string()`.
- **All 3 Faust templates compile** in DawDreamer (`set_dsp_string` returned True for each) — verified beyond the plan's static `os.osc`/`en.adsr` string check.
- **manifest.py** fails loud (`IngestError` naming the pair) on bad spec_version, bad/missing algorithm, operator count != 3, missing fields, out-of-range values, bools, and NaN/Inf.
- Full suite green: **166 passed** (was 159; the 7 extra are pre-existing tests collected, no regression).

## Task Commits

1. **Task 1: Add dawdreamer dependency + verify single-venv coexistence (A4)** - `0825d68` (chore)
2. **Task 2: apollo/synth/spec.py — FM single source of truth** - `dc615cf` (feat)
3. **Task 3: apollo/synth/manifest.py validator + package __init__** - `b5d4b52` (feat)

## Files Created/Modified
- `pyproject.toml` - Added `dawdreamer==0.8.3` (exact pin) to `[project].dependencies`
- `apollo/synth/spec.py` - FM schema, 3 algorithms, envelope semantics, engine consts, `dsp_string()`
- `apollo/synth/manifest.py` - `load_manifest(path, pair_path) -> FmParams` with version+shape+range validation
- `apollo/synth/__init__.py` - package public surface (spec + manifest symbols; no `.render` yet)

## Decisions Made
See key-decisions in frontmatter. Notable: the per-op slider naming scheme and the modulation-depth convention are now load-bearing contracts that render.py (06-02) must honor when resolving `get_parameters_description()` name->index maps.

## Final operator slider naming scheme (for render.py / Plan 06-02)
`dsp_string` emits these settable hsliders per operator (i in 1..3):
`op{i}_ratio`, `op{i}_level`, `op{i}_attack`, `op{i}_decay`, `op{i}_sustain`, `op{i}_release`.
`freq`/`gain`/`gate` are MIDI-owned (NOT settable). render.py must build a name->index map at runtime via `get_parameters_description()` — do NOT hardcode indices (spike landmine).

## Manifest range decisions (vs. proposed)
No deviation from proposed ranges: ratio [0.5,12], level [0,1], gain [0,1], attack/decay/release [0,2] s, sustain [0,1], exactly 3 operators. Added explicit bool rejection (a JSON `true`/`false` is not a valid numeric param) beyond the plan's NaN/Inf guard.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Reject JSON booleans in numeric fields**
- **Found during:** Task 3 (manifest validation)
- **Issue:** Python `isinstance(True, int)` is True, so a JSON `true` would pass an int/float check and flow into a numeric param.
- **Fix:** `_check_number` rejects `bool` before the numeric check; `algorithm` guard also rejects bools.
- **Files modified:** apollo/synth/manifest.py
- **Verification:** validation harness covers bad-algorithm path; bool would raise IngestError.
- **Committed in:** `b5d4b52`

**2. [Rule 2 - Missing Critical] Top-level type guards (object / list)**
- **Found during:** Task 3
- **Issue:** Plan specified field guards but a non-object manifest or non-list `operators` would raise an opaque error instead of a pair-named IngestError.
- **Fix:** Added `isinstance(raw, dict)` and `isinstance(ops, list)` guards raising IngestError.
- **Files modified:** apollo/synth/manifest.py
- **Committed in:** `b5d4b52`

---

**Total deviations:** 2 auto-fixed (both Rule 2 — security/correctness at the trust boundary)
**Impact on plan:** Both reinforce the T-06-01 Tampering mitigation. No scope creep.

## Issues Encountered
None. The `__init__.py` was written alongside spec.py but imports `.manifest`, so it was committed with Task 3 to keep the package importable at each commit; spec.py was verified directly via its module path for Task 2.

## Threat Surface
No new surface beyond the plan's `<threat_model>`. Mitigations T-06-01 (finite+range+type checks), T-06-02 (spec_version reject), T-06-03 (numeric-only dsp_string), T-06-04 (op-count reject) are all implemented.

## Next Phase Readiness
- 06-02 (render.py) can import `FmParams, dsp_string, SR, BLOCK, NUM_VOICES, TARGET_PEAK` from `apollo.synth.spec` and `load_manifest` from `apollo.synth.manifest`.
- A4 cleared — render.py may assume torch and dawdreamer share the project venv.
- Slider naming + modulation convention documented above for the runtime name->index resolution.

## Self-Check: PASSED

---
*Phase: 06-synth-independent-corpus-rendering*
*Completed: 2026-06-02*

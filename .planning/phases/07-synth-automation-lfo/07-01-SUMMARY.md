---
phase: 07-synth-automation-lfo
plan: 01
subsystem: synth
tags: [faust, dawdreamer, lfo, fm-synth, spec-versioning, manifest-validation]

# Dependency graph
requires:
  - phase: 06-synth-independent-corpus-rendering
    provides: "owned 3-op FM synth (spec.py SPEC_VERSION 1.0, manifest.py fail-loud loader, render.py deterministic DawDreamer driver)"
provides:
  - "FM spec v1.1 — optional global LFO (rate/depth/wave/target) on FmParams.lfo"
  - "LfoWave/LfoTarget IntEnums + frozen LfoParams (single source of truth for Phase 5 browser-synth parity)"
  - "numeric-only dsp_string LFO branch (level tremolo + pitch vibrato), verbatim v1.0 source when lfo is None"
  - "manifest loader accepting spec_version {1.0,1.1} with lfo-requires-1.1 cross-check and fail-loud lfo validation"
  - "render.py sets lfo_rate/lfo_depth/lfo_wave by runtime label->index, guarded on params.lfo presence"
affects: [05-browser-synth, 03-corpus-inference, corpus-conventions]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Backward-compat by emitting the exact prior-version DSP source when an optional field is absent (RESEARCH Pitfall 1)"
    - "Numeric-only DSP dispatch: waveform via select3(int(lfo_wave),...), target via a Python branch choosing numeric wiring — no enum name interpolated"
    - "Optional manifest block validated fail-loud (range/finite/enum/bool) + version cross-check"

key-files:
  created: []
  modified:
    - apollo/synth/spec.py
    - apollo/synth/manifest.py
    - apollo/synth/render.py
    - apollo/synth/__init__.py
    - tests/test_synth_render.py

key-decisions:
  - "Vibrato max deviation = 50 cents at depth=1 (orchestrator default A1; baked Faust literal; discuss-phase could refine to 100)"
  - "CARRIER_PAIR LFO applied to ALL carriers uniformly (orchestrator default A4; one global LFO => both carriers move together)"
  - "No-lfo path emits the verbatim Phase-6 v1.0 DSP string (not depth-0 wiring) to preserve bit-identity"

patterns-established:
  - "Optional v1.1 field is the TRAILING dataclass field (lfo: LfoParams | None = None) so v1.0 positional/keyword constructors are unchanged"
  - "render.py guards the lfo slider-set block on params.lfo is not None (no-lfo dsp_string emits no lfo_* sliders to look up)"

requirements-completed: [SYNTH-01]

# Metrics
duration: ~25min
completed: 2026-06-02
---

# Phase 7 Plan 01: Synth Automation (LFO) — v1.1 Spec Core Summary

**FM spec bumped to v1.1 with one optional global LFO (sine/triangle/square; tremolo or vibrato), backward-compatible by emitting the verbatim Phase-6 source when absent, numeric-only and deterministic across the three coordinated apollo/synth/ modules plus the package-root re-export.**

## Performance

- **Duration:** ~25 min
- **Tasks:** 3 (all TDD)
- **Files modified:** 5

## Accomplishments
- `spec.py`: `SPEC_VERSION` 1.0 -> 1.1; added `LfoWave`/`LfoTarget` IntEnums + frozen `LfoParams`; `FmParams` gained trailing optional `lfo` field; `dsp_string` branches — verbatim v1.0 body when `lfo is None`, numeric-only LFO block otherwise.
- `manifest.py`: relaxed version guard to `{"1.0","1.1"}`, added `_check_enum_int`, added LFO bounds, optional-lfo validation (reject under 1.0, reject non-object, fail-loud per field), threaded `lfo` into `FmParams`.
- `render.py`: sets `lfo_rate`/`lfo_depth`/`lfo_wave` by runtime label->index, guarded on `params.lfo is not None` (target excluded — compile-time branch).
- `__init__.py`: re-exported `LfoParams`/`LfoWave`/`LfoTarget` (import + `__all__`) so spec is the single source of truth at the package root.
- Added LFO tests (spec, manifest accept/reject, render determinism/diff/no-clip/pitch); full suite green (195 passed).

## Exact LFO Faust block emitted

Declarations (when `lfo` present), numeric-only:
```faust
lfo_rate = hslider("lfo_rate", <rate:.6f>, 0.05, 20, 0.001);
lfo_depth = hslider("lfo_depth", <depth:.6f>, 0, 1, 0.001);
lfo_wave = hslider("lfo_wave", <int wave>, 0, 2, 1);
lfo_bi = select3(int(lfo_wave), os.osc(lfo_rate), os.lf_triangle(lfo_rate), os.lf_squarewave(lfo_rate));
```

LEVEL target (tremolo) — `lvl_mod` multiplied into each carrier (both car1 and car2 for CARRIER_PAIR):
```faust
lfo_uni = (lfo_bi + 1.0) / 2.0;
lvl_mod = 1.0 - lfo_depth * (1.0 - lfo_uni);
// ... car ... * op1_level * lvl_mod
```

PITCH target (vibrato) — each carrier oscillator's freq arg scaled by `pitch_mul`:
```faust
pitch_mul = pow(2.0, (lfo_bi * lfo_depth * 50.0) / 1200.0);
// ... os.osc(freq * op1_ratio * pitch_mul + mod2) ...
```

- **Vibrato max-cents literal:** `50.0` (orchestrator default A1; baked Faust numeric literal, commented; discuss-phase could refine to 100 for dramatic).
- **CARRIER_PAIR application:** ALL carriers uniformly (orchestrator default A4; commented). For the pitch target, `car2` is re-emitted as `os.osc(freq * op2_ratio * pitch_mul) * op2_env * op2_level` so the second carrier also vibratos (the Phase-6 `op2` term carried no `pitch_mul`).
- **Package re-export confirmed:** `LfoParams`/`LfoWave`/`LfoTarget` added to `apollo/synth/__init__.py` (`.spec` import line + `__all__`); `from apollo.synth import LfoParams, LfoWave, LfoTarget` resolves.

## Task Commits

1. **Task 1: spec.py v1.1 + LFO schema + dsp_string branch + __init__ re-export** — `2aeab90` (feat, TDD)
2. **Task 2: manifest.py accept {1.0,1.1} + fail-loud LFO validation** — `adf0b71` (feat, TDD)
3. **Task 3: render.py LFO sliders by runtime index, guarded** — `c074ff5` (feat, TDD)

## Files Created/Modified
- `apollo/synth/spec.py` — SPEC_VERSION 1.1; LfoWave/LfoTarget/LfoParams; FmParams.lfo; dsp_string branch + `_body_no_lfo`/`_body_lfo_level`/`_body_lfo_pitch` helpers.
- `apollo/synth/manifest.py` — SUPPORTED_VERSIONS, LFO bounds, `_check_enum_int`, relaxed version guard, optional-lfo validation block.
- `apollo/synth/render.py` — guarded lfo slider-set block after the per-op loop.
- `apollo/synth/__init__.py` — re-export of LfoParams/LfoWave/LfoTarget.
- `tests/test_synth_render.py` — `_fm_params`/`_manifest_dict` `lfo=`/`spec_version=` kwargs; spec, manifest, and render LFO tests.

## Decisions Made
- Emit the verbatim Phase-6 v1.0 DSP string when `lfo is None` (bit-identity by same source, not depth-0 wiring) — RESEARCH Pitfall 1.
- Vibrato 50-cent max (A1) and all-carriers CARRIER_PAIR application (A4) — both orchestrator defaults, marked in code comments as refinable in discuss-phase.

## Deviations from Plan

None — plan executed exactly as written. No lfo bounds were altered (rate [0.05,20], depth [0,1], wave {0,1,2}, target {0,1} as specified).

## Issues Encountered
- The plan's Task-2 verify snippet had a typo (a `load_manifest(...)` call missing the required `pair_path` arg); the production code is correct and the equivalent corrected snippet plus the `pytest` suite both pass. No code change implied.
- Empirical observation (not a deviation): with the authored LFO values baked into the hslider defaults, an LFO render already differs from no-lfo even before `render.py` sets the sliders. The explicit runtime set was still added per the plan/Pitfall-3 (robustness — authored values must not depend on default-baking).

## Next Phase Readiness
- v1.1 spec contract is in place for plan 07-02 (golden-string bit-identity + determinism/time-variation tests) and 07-03 (CORPUS-CONVENTIONS.md doc).
- Phase 5 browser synth can mirror `spec.py` LfoWave/LfoTarget/LfoParams + the tremolo formula `1 - depth*(1-unipolar)` and vibrato formula `pow(2, lfo_bi*depth*50/1200)`.
- No blockers.

## Self-Check: PASSED

- apollo/synth/spec.py — FOUND, SPEC_VERSION "1.1", LfoWave/LfoTarget/LfoParams present
- apollo/synth/manifest.py — FOUND, SUPPORTED_VERSIONS + _check_enum_int + lfo block present
- apollo/synth/render.py — FOUND, `params.lfo is not None` guard present
- apollo/synth/__init__.py — FOUND, LfoParams/LfoWave/LfoTarget re-exported
- Commits 2aeab90, adf0b71, c074ff5 — all present in git log
- `.venv/bin/python -m pytest -q` — 195 passed

---
*Phase: 07-synth-automation-lfo*
*Completed: 2026-06-02*

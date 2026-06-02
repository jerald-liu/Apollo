---
phase: 07-synth-automation-lfo
plan: 02
subsystem: synth
tags: [tests, lfo, bit-identity, determinism, mel-time-variation, manifest-validation, golden-fixture]

# Dependency graph
requires:
  - phase: 07-synth-automation-lfo
    plan: 01
    provides: "v1.1 LFO spec core (spec.py dsp_string LFO branch + verbatim v1.0 body, manifest fail-loud lfo validation, render.py runtime slider set, package re-exports)"
provides:
  - "Committed verbatim v1.0 dsp_string golden fixtures (one per algorithm) anchoring backward-compat bit-identity against ANY v1.0-body drift"
  - "Executable proof of SYNTH-01 SC#1 (mel time-variation), SC#2 (no-lfo + depth-0 bit-identity), SC#3 (determinism), SC#5 (mel contract) + no-clip"
  - "Always-run manifest validation tests for the v1.1 lfo trust boundary (accepts-v11, requires-v11, rate/wave/target/NaN rejection)"
affects: [07-03-corpus-conventions-doc]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Bit-identity anchored to a committed verbatim golden source string (read from fixture, NOT recomputed from dsp_string) so the assertion is non-tautological"
    - "Mel time-variation made separable by raising LFO depth (not loosening the cosine threshold) when the RESEARCH baseline margin is thin"

key-files:
  created:
    - tests/fixtures/dsp_v1_0/stack.dsp
    - tests/fixtures/dsp_v1_0/parallel_mods.dsp
    - tests/fixtures/dsp_v1_0/carrier_pair.dsp
  modified:
    - tests/test_synth_render.py

key-decisions:
  - "v1.0 golden anchor form = committed fixture FILES under tests/fixtures/dsp_v1_0/ (form (a)), read at test time — not in-file constants"
  - "test_lfo_depth0_matches_static held bit-identical via np.array_equal (maxdiff 0.0) — no mel-cosine relaxation needed"
  - "Time-variation test uses 6 Hz / depth 1.0 (measured cos=0.997650) rather than the RESEARCH 6 Hz/0.8 baseline (cos=0.998722) for a comfortable margin below 0.999 — threshold NOT loosened"

requirements-completed: [SYNTH-01]

# Metrics
duration: ~20min
completed: 2026-06-02
---

# Phase 7 Plan 02: LFO Test Suite — Bit-Identity, Determinism, Time-Variation, Validation Summary

**Proved the v1.1 LFO contract end-to-end: a committed verbatim v1.0 dsp_string golden (one per algorithm) anchors no-lfo bit-identity against ANY source drift, depth-0 renders are bit-identical to static (np.array_equal, maxdiff 0.0), a 6 Hz/depth-1.0 tremolo is measurably time-varying through the frozen mel (cos=0.997650 < 0.999), and the manifest boundary rejects every malformed lfo block — full suite 204 passed.**

## Performance

- **Duration:** ~20 min
- **Tasks:** 2 (both type=auto)
- **Files created:** 3 (golden fixtures); **modified:** 1 (test file)

## Test counts

- **Before (after 07-01):** 195 passed
- **After (07-02):** 204 passed (+9 tests: golden anchor, accepts-v11, v10-no-lfo, target-bad-enum in Task 1; absent-bit-identical, depth0-matches-static, time-varies, mel-contract, no-clipping in Task 2)
- Full suite: `.venv/bin/python -m pytest -q` → **204 passed in ~17 s**, exit 0.

## Accomplishments

### Task 1 — golden anchor + always-run validation (commit `55a0d58`)
- Captured the EXACT current v1.0 `dsp_string` output per algorithm and committed it as fixture files `tests/fixtures/dsp_v1_0/{stack,parallel_mods,carrier_pair}.dsp`.
- `test_dsp_string_v1_0_golden` (always-run, no dawdreamer): asserts `dsp_string(_fm_params(algorithm=N)) == <golden file N>` for all three algorithms — ANY drift in the v1.0 body fails, not just `lfo_` introduction.
- Added plan-named validation tests `test_manifest_accepts_v11`, `test_manifest_v10_no_lfo_still_loads`, `test_lfo_target_bad_enum` (the 07-01 suite already carried `test_lfo_requires_v11`, `test_lfo_rate_out_of_range`, `test_lfo_wave_bad_enum`, `test_lfo_nan_rate`, `test_manifest_bad_version`).

### Task 2 — LFO render contract (commit `7f4221a`)
- `test_lfo_absent_bit_identical`: no-lfo render deterministic (`np.array_equal`) AND `dsp_string(no_lfo) == _GOLDEN_V1_0[0]` (the strong `==`-against-golden anchor, not the weaker `"lfo_" not in`).
- `test_lfo_depth0_matches_static`: depth-0 lfo render `np.array_equal` to the static render.
- `test_lfo_time_varies`: 6 Hz / depth-1.0 tremolo vs depth-0 static, mel `cosine_similarity < 0.999`.
- `test_lfo_mel_contract`: lfo render → MelExtractor → `(96,128)` `torch.float32`.
- `test_lfo_no_clipping`: deep square-wave (`LfoParams(6.0,1.0,2,0)`) render `<= 1.0`.
- Determinism (SC#3) was already covered by `test_lfo_render_deterministic` from 07-01.

## Measured values (required by plan output)

- **v1.0 golden anchor form:** committed fixture FILES (form (a)), `tests/fixtures/dsp_v1_0/*.dsp`, read at test time.
- **`test_lfo_depth0_matches_static`:** held **bit-identical** via `np.array_equal` (measured maxdiff `0.0`) — no mel-cosine relaxation needed.
- **`test_lfo_time_varies` measured cosine (lfo vs static, through the frozen MelExtractor):**

  | rate (Hz) | depth | measured cos | margin below 0.999 |
  |-----------|-------|--------------|--------------------|
  | 6.0 | 0.8 (RESEARCH baseline) | 0.998722 | ~0.00028 (thin) |
  | 6.0 | 0.9 | 0.998248 | ~0.00075 |
  | 8.0 | 1.0 | 0.997753 | ~0.00125 |
  | **6.0** | **1.0 (CHOSEN)** | **0.997650** | **~0.00135 (comfortable)** |

  Chose **6 Hz / depth 1.0** (cos=0.997650) — a ~4.5× wider margin than the RESEARCH 6 Hz/0.8 baseline (0.998722). The 0.999 threshold was **NOT** loosened; the modulation was made more separable by raising depth (rate held at 6 Hz per Pitfall 4, not the 0.05 Hz edge). Note: RESEARCH reported cos=0.9990 at 6 Hz/0.8; this session measured 0.998722 at the same point (still under threshold, but thin — hence the depth bump).

## dawdreamer skip behavior

- dawdreamer 0.8.3 present in `.venv` (arm64/Py3.11), so all render tests ran. The benign `undefined symbol : effect` DawDreamer warnings appear on stderr during compile (documented spike landmine) and do not affect results. On non-arm64 CI the render block `importorskip`s; the golden + validation tests (above the importorskip) always run.

## Deviations from Plan

None affecting scope. Minor notes:
- The 07-01 executor had already added `lfo=`/`spec_version=` helper kwargs and several LFO render/validation tests; Task 1's helper extensions were therefore already in place, so this plan added the plan-named tests that were still missing (golden anchor, `accepts_v11`, `v10_no_lfo_still_loads`, `target_bad_enum`) rather than re-adding the pre-existing ones. No duplicate-name collisions.
- Used golden fixture FILES (form (a)) over in-file constants for readability and to keep the 1 KB triple-quoted source out of the test module.

## Self-Check: PASSED

- tests/fixtures/dsp_v1_0/stack.dsp — FOUND
- tests/fixtures/dsp_v1_0/parallel_mods.dsp — FOUND
- tests/fixtures/dsp_v1_0/carrier_pair.dsp — FOUND
- tests/test_synth_render.py — FOUND (611 lines; all 7 required test defs present)
- Commit 55a0d58 (Task 1) — present in git log
- Commit 7f4221a (Task 2) — present in git log
- `.venv/bin/python -m pytest -q` — 204 passed, exit 0
- No committed `.wav` fixtures (tests/*.wav absent)

---
*Phase: 07-synth-automation-lfo*
*Completed: 2026-06-02*

---
phase: 07-synth-automation-lfo
reviewed: 2026-06-02T18:08:20Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - apollo/synth/spec.py
  - apollo/synth/manifest.py
  - apollo/synth/render.py
  - apollo/synth/__init__.py
  - tests/test_synth_render.py
findings:
  critical: 0
  warning: 0
  info: 3
  total: 3
status: issues_found
---

# Phase 7: Code Review Report

**Reviewed:** 2026-06-02T18:08:20Z
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

Reviewed the Phase 7 optional-LFO addition to the FM synth: `spec.py` v1.1
(LfoParams/LfoWave/LfoTarget enums, numeric-only `dsp_string` LFO branch),
`manifest.py` validation, `render.py` runtime slider wiring, the package
re-export, and the test suite.

The three focus areas all hold up:

- **Injection safety (numeric-only DSP).** Every value that reaches the Faust
  source is forced through `float(...)`/`int(...)` formatting before
  interpolation — `lfo_rate`/`lfo_depth` as `:.6f`, `lfo_wave` as `int(...)`,
  the 50.0-cent and select3 literals are baked Python constants. No manifest
  string field exists, and `_check_number`/`_check_enum_int` reject bools,
  non-numerics, and NaN/Inf at the trust boundary. The `target` enum selects a
  Python branch, never interpolating its name. I found no path by which an
  authored string reaches the DSP source.
- **LFO validation.** Bounds (rate [0.05,20], depth [0,1]), enum membership
  (wave {0,1,2}, target {0,1}), the `lfo`-requires-`1.1` cross-check, and the
  `spec_version ∈ {1.0,1.1}` guard are all fail-loud and well-tested
  (`test_lfo_*` + `test_lfo_requires_v11`).
- **Backward-compat bit-identity.** The `lfo is None` branch emits the verbatim
  Phase-6 source, anchored byte-for-byte against committed golden fixtures
  (`test_dsp_string_v1_0_golden`) — I confirmed `dsp_string` output equals
  `tests/fixtures/dsp_v1_0/stack.dsp`. The 18 non-dawdreamer tests pass locally.

No correctness, security, or logic defects found. The three Info items below are
test-coverage and robustness observations, not bugs. Nothing here blocks the
phase.

## Info

### IN-01: Depth-0 bit-identity is only asserted for the LEVEL target, not PITCH

**Status: CLOSED** (characterized 2026-06-02)

**File:** `tests/test_synth_render.py:364-377`
**Issue:** `test_lfo_depth0_matches_static` proves a depth-0 LFO renders
bit-identically to the no-LFO path, but only for `LfoParams(6.0, 0.0, 0, 0)`
(target=LEVEL). The PITCH target takes a different `dsp_string` body
(`_body_lfo_pitch`), and for CARRIER_PAIR it does not merely multiply by a
`*1.0` factor — it *replaces* the `car2 = op2 * op2_level` expression with a
freshly re-emitted `car2 = os.osc(freq * op2_ratio * pitch_mul) * op2_env *
op2_level` (spec.py:320-324). At depth 0, `pitch_mul` is `pow(2,0)=1.0`, so this
is *mathematically* equal to the `op2` macro, but it is a structurally different
Faust expression whose sample-level identity relies on the compiler folding
`* 1.0` and CSE-ing the two oscillator instances identically. The depth-0 ==
static guarantee for the pitch/CARRIER_PAIR combination is asserted nowhere.

**Resolution:** `test_lfo_pitch_depth0_matches_static` added covering all three
algorithms. Findings:
- PARALLEL_MODS (1) and CARRIER_PAIR (2): **bit-identical** (`array_equal` passes).
  The CARRIER_PAIR re-emission of `car2` folds correctly — LLVM CSEs the two
  identical oscillator instances.
- STACK (0): **not bit-identical** — max abs diff ~6.7e-5 (rel ~7.5e-5). The
  divergence is a compiler float-reassociation artifact: `freq * op1_ratio *
  pitch_mul` inside `os.osc()` compiles differently from `freq * op1_ratio` even
  when `pitch_mul == 1.0`. The render is fully deterministic and numerically
  equivalent (`allclose atol=1e-4`); the diff is inaudible and below the mel floor.

Depth-0 bit-identity is a LEVEL-target property. For PITCH the guarantee is
numerical equivalence (allclose), not byte identity for STACK. Documented in
`spec.py` (the `else: # LfoTarget.PITCH` block) and encoded in the test with
per-algorithm assertions.

### IN-02: `_check_enum_int` rejects integral floats that JSON-load equivalently

**File:** `apollo/synth/manifest.py:113-114`
**Issue:** `_check_enum_int` requires `isinstance(value, int)`, so a manifest
written as `"wave": 0.0` (an integral float, which is a perfectly common way for
a hand-editor or a serializer to emit an enum value) is rejected with "must be
an int". The numeric fields use `_check_number`, which tolerates this, so the
two paths diverge in author-facing strictness. This is a deliberate, safe
choice (rejecting `0.0` is conservative and the error is clear), but it is a
papercut for hand-authored corpora and worth a one-line doc note in the manifest
schema so authors know enum fields must be JSON integers, not floats.
**Fix:** Either document "wave/target must be JSON integers (not 0.0)" in the
module docstring schema block, or accept integral floats:
`isinstance(value, int) or (isinstance(value, float) and value.is_integer())`
then coerce with `int(value)`. The doc note is the lower-risk option and keeps
the strict-int invariant.

### IN-03: LFO `rate`/`depth`/`wave` missing-field errors surface as a range/type message, not "missing field"

**File:** `apollo/synth/manifest.py:187-190`
**Issue:** Per-operator fields get an explicit `"operator {idx} missing field
{field!r}"` message (manifest.py:168-169), but the LFO fields use
`raw_lfo.get("rate")` etc., so an omitted `rate` passes `None` straight into
`_check_number`, producing "lfo rate must be a number, got NoneType" rather than
a "missing field 'rate'" message. The validation is still fail-loud and correct
(None is rejected), only the diagnostic is slightly less precise than the
operator path's. Minor inconsistency in error ergonomics, not a correctness
issue.
**Fix:** Mirror the operator-field pattern for parity, e.g.:
```python
for f in ("rate", "depth", "wave", "target"):
    if f not in raw_lfo:
        raise IngestError(pair_path, f"lfo missing field {f!r}")
```
before extracting values. Optional — the current behavior is safe.

---

_Reviewed: 2026-06-02T18:08:20Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

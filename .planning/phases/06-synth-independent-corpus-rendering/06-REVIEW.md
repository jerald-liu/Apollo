---
phase: 06-synth-independent-corpus-rendering
reviewed: 2026-06-02T00:00:00Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - apollo/synth/spec.py
  - apollo/synth/manifest.py
  - apollo/synth/render.py
  - apollo/synth/__init__.py
  - apollo/scripts/render_corpus.py
  - apollo/scripts/generate.py
  - tests/test_synth_render.py
  - tests/test_generate.py
  - pyproject.toml
findings:
  critical: 0
  warning: 3
  info: 4
  total: 7
status: issues_found
---

# Phase 6: Code Review Report

**Reviewed:** 2026-06-02T00:00:00Z
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

Phase 6 delivers a synth-independent corpus rendering pipeline (DawDreamer + Faust
3-operator FM) with a clean single-shared-entrypoint design (`render_call_wav`) that
genuinely enforces train/serve parity. The domain's highest-risk concerns are handled
well:

- **DSP injection (T-06-01/03):** `dsp_string` only ever interpolates `float(...)`-cast
  numeric values; no manifest string can reach the Faust source. Verified across all
  three algorithm templates and the per-op slider/ADSR declarations.
- **Manifest trust boundary:** `load_manifest` is fail-loud, rejects bools, NaN/Inf
  (`math.isfinite`), out-of-range values, wrong operator counts, and unknown
  `spec_version` — each with an `IngestError` naming the pair. Mirrors the existing
  `midi.py` discipline well.
- **Poly-param-by-index landmine:** `_build_name_index_map` resolves slider names to
  indices at runtime from `get_parameters_description()`, never hardcoding an index, and
  fails loud if an expected slider is missing.
- **Headroom before PCM write:** peak normalization to `TARGET_PEAK` (0.89) happens
  before any `sf.write`, and the no-clip test asserts `<= 1.0`.
- **DoS cap (T-06-06):** render duration is checked against `MAX_RENDER_SECONDS` before
  the engine runs.
- **Train/serve parity verified:** `tempo_bpm` in `load_notes` is validation-only — note
  times come straight from pretty_midi in seconds — so the BPM divergence between
  `render_corpus` (`--tempo-bpm` default 120) and `generate.py` (`estimate_tempo()`)
  does NOT perturb the rendered audio. The render is a function of notes + manifest only.

No critical issues. The warnings below concern determinism robustness, an unbounded
helper loop, and a silently-ignored function argument. Info items are minor.

## Warnings

### WR-01: Peak normalization is non-deterministic for an all-silent render

**File:** `apollo/synth/render.py:156-157`
**Issue:** `peak = float(np.max(np.abs(audio)))` then `audio / max(peak, 1e-9) * TARGET_PEAK`.
For a normal render this is fine and deterministic. But if a render produces all-zero
(or near-silent) output — e.g. a manifest where every operator `level` and the carrier
contribution sum to silence, or a gate/envelope edge case — `peak` is ~0 and the divide
falls back to `1e-9`, multiplying tiny numerical noise by `TARGET_PEAK / 1e-9 ≈ 8.9e8`.
That amplifies sub-denormal floating-point dust into full-scale garbage, and whether it
exceeds 1.0 depends on engine-internal noise floor (a determinism/clipping hazard the
`test_no_clipping` fixture would never catch because it uses a healthy preset). The
"silent render" case is reachable from valid in-range manifests (all `level=0`).
**Fix:** Guard the silent case explicitly rather than relying on the epsilon to paper
over it — leave silence as silence:
```python
peak = float(np.max(np.abs(audio)))
if peak > 1e-6:
    audio = audio / peak * TARGET_PEAK
# else: render is effectively silent; leave as-is (do not amplify noise floor)
```

### WR-02: `render_call_wav` silently ignores `mid_path` when `notes` is supplied

**File:** `apollo/synth/render.py:162-184` (and caller `apollo/scripts/generate.py:201-207`)
**Issue:** When `generate.py` passes `notes=call_notes`, the `mid_path` argument
(`str(call_mid_path)`) is accepted but never used — `load_notes` is skipped. This is the
intended optimization (avoid double-parsing), but the signature lets a caller pass a
`mid_path` and a `notes` list that describe *different* MIDI, and the function will
silently render the `notes` while appearing to render `mid_path`. There is no assertion
tying them together. For a parity-critical entrypoint this is a latent footgun: a future
caller could desync them and the bug would be invisible (the wav would not match the
MIDI the corpus pipeline would produce).
**Fix:** Either make the two paths mutually exclusive in the signature, or document the
precedence loudly at the call boundary. Minimal version — assert intent so a desync is
caught in tests:
```python
def render_call_wav(manifest_path, mid_path=None, *, pair_path, call_bpm=120.0, notes=None):
    params = load_manifest(manifest_path, pair_path)
    if notes is None:
        if mid_path is None:
            raise IngestError(pair_path, "render_call_wav requires either mid_path or notes")
        notes = load_notes(mid_path, pair_path, tempo_bpm=call_bpm)
    return render(params, notes, pair_path=pair_path)
```
At minimum, add a comment at `render.py:182` noting `mid_path` is ignored when `notes` is
passed, so the dead-arg path is intentional and visible.

### WR-03: `_next_response_path` unbounded loop with no cap

**File:** `apollo/scripts/generate.py:48-55`
**Issue:** `_next_response_path` increments `idx` in a `while True` with no upper bound.
In normal use this terminates immediately, but it is the one unbounded loop in the
inference path. If a pair directory accumulates a very large number of `response_NNN.mid`
(or under an adversarial/automated-batch scenario), this becomes an O(n) filesystem stat
storm per call with no guard. The format string `f"response_{idx:03d}.mid"` also implies a
3-digit convention that silently breaks ordering past 999 (`response_1000.mid` sorts
before `response_002.mid`).
**Fix:** Add a sane cap and fail loud past it:
```python
def _next_response_path(pair_dir: Path, max_idx: int = 999) -> Path:
    for idx in range(1, max_idx + 1):
        candidate = pair_dir / f"response_{idx:03d}.mid"
        if not candidate.exists():
            return candidate
    raise IngestError(str(pair_dir), f"more than {max_idx} responses; clean up the pair dir")
```

## Info

### IN-01: Render-duration cap duplicates `MelExtractor.MAX_WAV_SECONDS` as a literal

**File:** `apollo/synth/render.py:56`
**Issue:** `MAX_RENDER_SECONDS = 30.0` is a hand-copied mirror of
`MelExtractor.MAX_WAV_SECONDS = 30.0` (confirmed in `apollo/ingest/audio.py:45`). The
comment documents the coupling, but the two constants can drift independently — if
`MAX_WAV_SECONDS` is ever changed, this silently desyncs and a render could be capped
inconsistently with the mel stage.
**Fix:** Import and reference the source of truth: `from apollo.ingest.audio import MelExtractor; MAX_RENDER_SECONDS = MelExtractor.MAX_WAV_SECONDS` (or hoist a shared constant), so the cap cannot drift.

### IN-02: `estimate_tempo()` is called twice in the inference path

**File:** `apollo/scripts/generate.py:185` (and again inside `load_notes` at `apollo/ingest/midi.py:90`)
**Issue:** `generate.py` computes `call_bpm = estimate_tempo()` on line 185, then calls
`load_notes(..., tempo_bpm=call_bpm)` which internally calls `estimate_tempo()` again to
validate against the value just derived from the same estimate. The validation is
therefore comparing the estimate to itself (always within tolerance) — the tempo guard is
effectively a no-op for the inference path. Not a correctness bug (the render does not
depend on bpm), but the guard provides no protection here, which may be surprising.
**Fix:** No code change required for parity; consider a brief comment noting the guard is
trivially satisfied in the inference path so a future reader does not assume it validates
anything.

### IN-03: Per-pair render failure aborts the entire corpus run

**File:** `apollo/scripts/render_corpus.py:74-90`
**Issue:** The loop renders pairs sequentially and the first `IngestError` aborts the
whole run (returns 1). For a 30+ pair corpus, one bad manifest means re-running everything
after each fix. This matches the documented exit-code contract ("Fix the corpus and
re-run") and mirrors `ingest_corpus`, so it is a deliberate choice — flagged only as a
usability note.
**Fix:** Optional: accumulate failures and report all bad pairs at once, or write the
successful `.wav`s incrementally (already happens) so re-runs only redo failed pairs. No
change required if the fail-fast contract is intended.

### IN-04: `dawdreamer` import inside `render` swallows engine import errors into generic exit 2

**File:** `apollo/synth/render.py:98`
**Issue:** `import dawdreamer as dd` is a local import (correctly deferred — heavy native
wheel). If the wheel is missing/broken at render time, the `ImportError` propagates as a
generic `Exception` to the CLI's catch-all (`render_corpus.py:91`, exit code 2), with a
raw `repr`. That is acceptable per the exit-code contract (2 = environment issue), but the
message will not clearly say "dawdreamer not installed."
**Fix:** Optional: catch `ImportError` at the call site (or in `render`) and raise a clear
environment-setup message. Low priority — exit code 2 already signals "environment issue."

---

_Reviewed: 2026-06-02T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

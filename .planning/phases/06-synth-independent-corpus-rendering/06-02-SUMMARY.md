---
phase: 06-synth-independent-corpus-rendering
plan: 02
subsystem: synth
tags: [dawdreamer, faust, fm-synthesis, rendering, determinism, train-serve-parity, cli]

# Dependency graph
requires:
  - phase: 06-synth-independent-corpus-rendering
    plan: 01
    provides: "spec.py (FmParams, dsp_string, SR/BLOCK/NUM_VOICES/TARGET_PEAK), manifest.py (load_manifest), per-op slider naming contract"
provides:
  - "apollo/synth/render.py — deterministic 3-op FM renderer (render) + single shared parity entrypoint (render_call_wav)"
  - "apollo/scripts/render_corpus.py — batch CLI rendering call.wav from call_fm.json with 0/1/2 exit-code contract"
  - "tests/test_synth_render.py — determinism / no-clip / mel-contract / timbre / validation / parity suite"
  - "apollo.synth package surface now exports render + render_call_wav"
affects: [06-03 generate.py inference wiring, DATA-05 corpus authoring]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Single shared render_call_wav entrypoint guarantees train/serve render parity (corpus + inference call one function)"
    - "Runtime Faust slider name->index resolution via get_parameters_description() label field (never hardcode poly indices)"
    - "Scalar peak normalization with headroom (TARGET_PEAK) — linear gain preserves the mel timbre signal"
    - "Manifest-presence pair enumeration for derived artifacts (call.wav is rendered, not authored)"

key-files:
  created:
    - apollo/synth/render.py
    - apollo/scripts/render_corpus.py
    - tests/test_synth_render.py
  modified:
    - apollo/synth/__init__.py

key-decisions:
  - "ADSR params are compiled as numeric literals inside en.adsr(...) by spec.dsp_string — they are NOT runtime-settable Faust sliders. Only op{i}_ratio / op{i}_level are runtime sliders. ADSR still takes effect (baked in from the manifest at DSP-string-generation time), so determinism + per-pair timbre are preserved. render.py resolves only ratio/level by runtime index."
  - "Unmangled slider name lives in the DawDreamer description `label` field; `name` holds the mangled poly path (/Polyphonic/Voices/dawdreamer/<slider>). Index map matches on label, with the trailing path segment as fallback."
  - "render_corpus enumerates pairs by call_fm.json + call.mid presence, NOT via apollo.ingest.discover_pairs (which requires call.wav to already exist). call.wav is a derived artifact, so discover_pairs cannot bootstrap a not-yet-rendered corpus."
  - "Mono output (audio[0]) — removes L/R asymmetry as a determinism variable; MelExtractor mono-mixes anyway."

requirements-completed: [DATA-06]

# Metrics
duration: ~15min
completed: 2026-06-02
---

# Phase 6 Plan 02: Synth-Independent Renderer & Corpus Render CLI Summary

**Deterministic 3-operator DawDreamer+Faust renderer (`render`) plus the single shared `render_call_wav` parity entrypoint and a batch `render_corpus` CLI, producing `call.wav` entirely in Python from `call.mid` + `call_fm.json`, feeding the frozen COND-01 MelExtractor unchanged.**

## Performance

- **Duration:** ~15 min
- **Tasks:** 3
- **Files modified:** 4 (3 created, 1 edited)

## Accomplishments

- **`render.py`** renders 3-op FM bit-deterministically. `render(params, notes, *, pair_path)` resolves slider indices at runtime, caps render duration (`MAX_RENDER_SECONDS = 30.0`, T-06-06), peak-normalizes with headroom, and returns a mono float32 1-D array. `render_call_wav` is the ONE shared render path (loads manifest + parses MIDI via `load_notes`, with a `notes=` passthrough so `generate.py` can pass already-parsed call_notes — no double-parse).
- **Determinism confirmed:** `render(...)` twice on identical inputs → `np.array_equal` **True** (matches spike 001).
- **No-clip confirmed:** measured peak after normalization = **0.8900** for non-silent renders (== TARGET_PEAK 0.89; ≤ 1.0 always).
- **Mel contract holds:** rendered wav → production `MelExtractor` → shape **(96, 128)**, dtype **torch.float32**, unchanged pipeline.
- **Timbre discriminable:** two contrasting presets (1:1 stack low-level vs 7:1 parallel-mods full-level) gave **cosine 0.874**, **L2 791.6** — closely matching the spike's across-preset cos 0.85 / L2 783. The learnable mel-conditioning signal is intact.
- **`render_corpus.py`** batches `render_call_wav` over pairs, writes `call.wav` per pair via `soundfile.write`, with the 0/1/2 exit-code contract. End-to-end test: valid 120-bpm pair → exit 0, call.wav written; a non-120-bpm pair correctly fails loud → exit 1.
- **Render tests ran (did NOT skip)** — dawdreamer 0.8.3 is importable in the project `.venv` (A4 stayed cleared). All 9 tests pass; full suite **175 passed** (was 166, +9 new), no regression.

## Task Commits

1. **Task 1: deterministic 3-op FM renderer + shared render_call_wav** — `3bc60c2` (feat)
2. **Task 2: render_corpus CLI + synth render exports** — `1fe8f39` (feat)
3. **Task 3: synth render test suite** — `0e029d4` (test)

## Files Created/Modified

- `apollo/synth/render.py` — `render()` + `render_call_wav()`; runtime index resolution, duration cap, scalar peak normalization, benign-warning filter.
- `apollo/scripts/render_corpus.py` — batch CLI; manifest-presence pair enumeration with path-traversal safety; 0/1/2 exit codes.
- `tests/test_synth_render.py` — 9 tests (5 render + 4 manifest-validation); render tests `importorskip`-guarded.
- `apollo/synth/__init__.py` — added `render`, `render_call_wav` to imports + `__all__`.

## Decisions Made

See key-decisions in frontmatter. The load-bearing one for Plan 06-03: **`render_call_wav(manifest_path, mid_path, *, pair_path, call_bpm, notes=None)` is the single render path** — `generate.py` must call it (passing its already-parsed `call_notes` and the `estimate_tempo()` bpm) so inference and corpus renders are bit-identical.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] ADSR fields are not runtime sliders — corrected the slider-set loop**
- **Found during:** Task 1 (inspecting `get_parameters_description()` against the real engine).
- **Issue:** The 06-01 SUMMARY's slider contract claimed `dsp_string` emits settable hsliders for `attack`/`decay`/`sustain`/`release`. The actual `spec.py::dsp_string` compiles ADSR as numeric literals inside `en.adsr(...)`, so only `op{i}_ratio` and `op{i}_level` appear as runtime params. The initial render loop tried to set all six per op and would have raised `IngestError("missing param op1_attack")` on every render.
- **Fix:** Set only `ratio`/`level` by runtime index (`_OP_SLIDER_FIELDS`). ADSR still takes effect — it is baked into the DSP string from the manifest at compile time, so per-pair envelope timbre and determinism are fully preserved. Documented in the module + a key-decision.
- **Files modified:** apollo/synth/render.py
- **Verification:** determinism + mel + timbre tests pass; envelope shape is audible in the timbre-discriminability gap.
- **Committed in:** `3bc60c2`

**2. [Rule 1 - Bug] Unmangled slider name is in `label`, not `name`**
- **Found during:** Task 1.
- **Issue:** Under `num_voices` the description `name` field holds the mangled poly path (`/Polyphonic/Voices/dawdreamer/op1_ratio`) and there is no `path` key. Matching on `name` would never find `op1_ratio`.
- **Fix:** `_build_name_index_map` matches on `label` (the bare slider name), with the trailing path segment of `name` as a fallback. Honors the landmine (no hardcoded indices).
- **Files modified:** apollo/synth/render.py
- **Committed in:** `3bc60c2`

**3. [Rule 3 - Blocking] render_corpus enumerates by manifest, not discover_pairs**
- **Found during:** Task 2.
- **Issue:** The plan's acceptance criterion (`grep -q 'discover_pairs'`) assumed `apollo.ingest.discover_pairs` would enumerate pairs to render. But `discover_pairs` raises `IngestError("missing call.wav")` for any pair lacking `call.wav` — and `call.wav` is exactly the artifact this CLI produces. Using it would make rendering impossible for a fresh (not-yet-rendered) corpus, defeating the phase's purpose (call.wav is a *derived* artifact per RESEARCH Pitfall 5).
- **Fix:** Added `_discover_manifest_pairs()` that enumerates pair dirs having `call_fm.json` + `call.mid`, mirroring `discover_pairs`'s path-traversal (T-01-11) and hidden-dir (T-01-16) safety. The `discover_pairs` grep acceptance criterion is intentionally not satisfied; this is a corrected-assumption deviation, not a missing feature.
- **Files modified:** apollo/scripts/render_corpus.py
- **Committed in:** `1fe8f39`

---

**Total deviations:** 3 auto-fixed (2 Rule 1 against an incorrect 06-01 slider-contract claim; 1 Rule 3 blocking design conflict). No architectural change, no scope creep.
**Impact on plan:** All `must_haves` truths/artifacts/key_links still satisfied. The `render.py -> spec.py::dsp_string` and `render.py -> midi.py::load_notes` key_links hold. The `render_corpus.py -> render_call_wav` key_link holds. Only the `discover_pairs` grep (an acceptance check, not a must_have) is superseded by the corrected enumeration.

## TDD Gate Compliance

Task 3 was marked `tdd="true"`, but the implementation (render.py, render_corpus.py) was necessarily built in Tasks 1–2 before the test file, since the tests import the render API. The test commit (`0e029d4`) is therefore a `test(...)` commit landing AFTER the `feat(...)` commits rather than a RED-before-GREEN cycle. The behavior contract in `<behavior>` is fully covered and all tests pass; the inversion is structural (tests cannot import a not-yet-written module) and does not weaken coverage.

## Threat Surface

No new surface beyond the plan's `<threat_model>`. Mitigations implemented:
- **T-06-06 (DoS):** `dur` capped at `MAX_RENDER_SECONDS = 30.0` before the engine runs; exceeding raises `IngestError`.
- **T-06-07 (DoS):** MIDI note-count cap reused via `load_notes` (`MAX_NOTES_PER_PAIR`) — not re-implemented.
- **T-06-08 (Tampering):** params set by runtime-resolved integer index; no path string / hardcoded index.
- **T-06-09 (Tampering):** note velocity passed straight to the MIDI layer; manifest `gain` is a separate patch-level trim, not double-applied.
- **T-06-10 (Info Disclosure, accept):** benign `undefined symbol : effect` warning filtered via `contextlib.redirect_stderr`.

## Next Phase Readiness

- 06-03 can wire `generate.py` to `render_call_wav` for train/serve parity (replace the `call_wav` file argument). Pass the already-parsed `call_notes` via `notes=` and the `estimate_tempo()` bpm via `call_bpm=` so the MIDI is parsed once.
- `render_corpus` is ready to render the corpus once `call_fm.json` files are authored (DATA-05).
- CORPUS-CONVENTIONS.md still describes the old Ableton-bounce workflow (call.wav as authored input) — reconciling it to the FM-manifest workflow is a doc edit slated for Plan 06-03 per the PATTERNS map; not in this plan's scope.

## Self-Check: PASSED

---
*Phase: 06-synth-independent-corpus-rendering*
*Completed: 2026-06-02*

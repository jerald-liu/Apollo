---
phase: 06-synth-independent-corpus-rendering
verified: 2026-06-02T10:20:00Z
status: passed
score: 16/16 must-haves verified
overrides_applied: 0
---

# Phase 6: Synth-Independent Corpus Rendering Verification Report

**Phase Goal:** Replace the manual Ableton/Operator call.wav bounce with an owned FM synth rendered headlessly in Python — a single source-of-truth FM spec, a deterministic 3-operator Faust renderer (via DawDreamer) driving a per-pair FM-param manifest + call.mid into call.wav, wired so the same engine renders inference-time calls with no domain gap.
**Verified:** 2026-06-02T10:20:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

These are the merged must-haves: 6 ROADMAP success criteria + the per-plan PLAN truths (deduplicated). All were verified against real code AND exercised live (dawdreamer is installed in `.venv`).

| #   | Truth (source) | Status | Evidence |
| --- | -------------- | ------ | -------- |
| 1   | SC1 — No Ableton: call.wav produced entirely in Python from call.mid + FM manifest | ✓ VERIFIED | `render_corpus /tmp/rcorp` rendered `call.wav` (exit 0) from `call.mid`+`call_fm.json` with no Ableton. CORPUS-CONVENTIONS has no bounce step (`grep -ci "bounce to audio"` = 0). |
| 2   | SC2 — Single FM spec: schema + algorithm set + envelope semantics in one versioned place | ✓ VERIFIED | `apollo/synth/spec.py`: `SPEC_VERSION="1.0"`, `Algorithm(IntEnum)` 3 members, frozen `FmParams`/`OperatorParams`, engine consts, `dsp_string()`. Consumed by `manifest.py` (validation) and `render.py` (DSP). |
| 3   | SC3 — Deterministic: re-rendering same manifest+MIDI is bit-identical | ✓ VERIFIED | Live: `np.array_equal(render(p,notes), render(p,notes))` → True. `test_render_deterministic` + `test_render_call_wav_parity` PASSED. |
| 4   | SC4 — Drop-in conditioning: rendered audio feeds existing MelExtractor unchanged to (96,128) | ✓ VERIFIED | Live: MelExtractor on rendered wav → shape (96,128), dtype torch.float32. `apollo/ingest/audio.py` not in any plan's files_modified (frozen). `test_mel_contract` PASSED. |
| 5   | SC5 — Hand-authorable: per-pair timbre is a small documented JSON manifest, no synth UI | ✓ VERIFIED | `call_fm.json` schema (spec_version/algorithm/3 operators/gain) documented in CORPUS-CONVENTIONS.md; `load_manifest` parses JSON; no UI. |
| 6   | SC6 — Train/serve parity: inference uses the same engine + manifest format as corpus | ✓ VERIFIED | `generate.py` line 201 calls the same `render_call_wav` as `render_corpus.py` line 78. Single shared entrypoint in `render.py`. |
| 7   | dawdreamer==0.8.3 coexists with torch in one venv (A4) | ✓ VERIFIED | Live: `import torch, dawdreamer` OK, `hasattr(dawdreamer,'RenderEngine')` True, torch 2.12.0. |
| 8   | dsp_string builds Faust from numeric params only (no manifest string reaches DSP) | ✓ VERIFIED | `spec.py::dsp_string(p: FmParams)` formats only float fields via `:.6f`; takes typed FmParams, no string field. 3 algorithms produce 3 distinct DSP sources. |
| 9   | Malformed/out-of-range/wrong-count/bad-version manifest raises IngestError naming the pair | ✓ VERIFIED | Live: 2-ops, ratio-range, NaN, bool, gain-range, bad-version all raised IngestError with pair path. `test_manifest_*` (4) PASSED. |
| 10  | Rendered audio peaks never exceed 1.0 (peak-normalized w/ headroom) | ✓ VERIFIED | Live: peak = 0.8900 == TARGET_PEAK 0.89. `test_no_clipping` PASSED. |
| 11  | `render_corpus data/pairs/` renders every pair, exit 0 success / 1 IngestError | ✓ VERIFIED | Live: valid pair → exit 0 "OK: rendered 1 call.wav"; bad manifest → "RENDER FAILED: [.../000] spec_version '9.9' != '1.0'" exit 1. Exit 2 path present in code. |
| 12  | One shared render_call_wav is the single render path | ✓ VERIFIED | `render.py::render_call_wav` is the only entrypoint; both `render_corpus.py` and `generate.py` import & call it. |
| 13  | generate.py parses call MIDI once, shares call_bpm + call_notes between render and tokenize | ✓ VERIFIED | `generate.py`: `call_bpm=estimate_tempo()` (L185), `call_notes=load_notes(...)` (L189), `render_call_wav(..., call_bpm=call_bpm, notes=call_notes)` (L201-207). `notes=` passthrough skips re-parse. |
| 14  | CORPUS-CONVENTIONS describes FM-manifest workflow, no Ableton bounce; call.wav derived | ✓ VERIFIED | No "bounce to audio"; documents call_fm.json schema, render_corpus step, call_fm.json-vs-render_manifest distinction (1 ref); `.venv/bin/python` only (no bare venv/). |
| 15  | REQUIREMENTS.md DATA-01/02 reconciled as superseded by DATA-06 | ✓ VERIFIED | Lines 10-11 carry "SUPERSEDED by DATA-06"; traceability rows 99-100 note supersession; DATA-06 row marked Done (Phase 6). |
| 16  | Rendered call.wav gitignored; test_generate migrated; full suite green | ✓ VERIFIED | `.gitignore` line 52 `data/pairs/**/call.wav`; `test_generate.py` no call.wav positional, uses call_fm.json fixture; `pytest -q` → 175 passed. |

**Score:** 16/16 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `apollo/synth/spec.py` | SPEC_VERSION, 3-member Algorithm, frozen FmParams/OperatorParams, engine consts, dsp_string | ✓ VERIFIED | 178 lines; all present; imported by manifest.py + render.py |
| `apollo/synth/manifest.py` | load_manifest with version+shape+range validation, fail-loud IngestError | ✓ VERIFIED | 135 lines; type/finite/range/bool/count/version guards; imports spec + IngestError |
| `apollo/synth/__init__.py` | spec + manifest + render public surface | ✓ VERIFIED | Exports SPEC_VERSION, Algorithm, FmParams, OperatorParams, dsp_string, load_manifest, render, render_call_wav |
| `pyproject.toml` | dawdreamer==0.8.3 | ✓ VERIFIED | Pin present; coexists with torch live |
| `apollo/synth/render.py` | deterministic render + shared render_call_wav | ✓ VERIFIED | 184 lines; runtime index resolution, MAX_RENDER_SECONDS cap, scalar-peak norm, benign-warning filter |
| `apollo/scripts/render_corpus.py` | batch CLI, 0/1/2 exit codes | ✓ VERIFIED | 97 lines; main(argv=None)->int; manifest-presence enumeration; exit-code contract live-tested |
| `tests/test_synth_render.py` | determinism/mel/timbre/no-clip/validation/parity | ✓ VERIFIED | 9 tests, all PASSED (ran, not skipped) |
| `apollo/scripts/generate.py` | render-from-call_fm.json via render_call_wav | ✓ VERIFIED | render_call_wav wired, single parse, mel step (1,1,96,128) unchanged |
| `data/pairs/CORPUS-CONVENTIONS.md` | de-Ableton FM-manifest guide | ✓ VERIFIED | call_fm.json schema + render_corpus step + render_manifest distinction |
| `.planning/REQUIREMENTS.md` | DATA-01/02 superseded-by-DATA-06 | ✓ VERIFIED | Reconciliation present |
| `.gitignore` | rendered call.wav ignored | ✓ VERIFIED | `data/pairs/**/call.wav` |
| `tests/test_generate.py` | migrated to render-from-manifest | ✓ VERIFIED | 5 tests PASSED; call_fm.json fixture; importorskip guard |

### Key Link Verification

| From | To | Via | Status |
| ---- | -- | --- | ------ |
| manifest.py | spec.py | imports SPEC_VERSION/FmParams/Algorithm | ✓ WIRED |
| manifest.py | ingest/errors.py | raises IngestError(pair_path, reason) | ✓ WIRED |
| render.py | ingest/midi.py::load_notes | single MIDI validation path | ✓ WIRED |
| render.py | spec.py::dsp_string | only DSP-string source, runtime index | ✓ WIRED |
| render_corpus.py | render.py::render_call_wav | batch loop calls shared entrypoint | ✓ WIRED |
| generate.py | render.py::render_call_wav | inference uses shared entrypoint (parity) | ✓ WIRED |
| generate.py | ingest/midi.py::load_notes | single parse shared via notes= | ✓ WIRED |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| render.py | audio | DawDreamer engine.get_audio() driven by Faust dsp_string + MIDI notes | Yes — live peak 0.89, non-silent, timbre-discriminable (cos 0.874 across presets) | ✓ FLOWING |
| generate.py | mel_batch | render_call_wav → temp wav → MelExtractor | Yes — real (1,1,96,128) tensor from rendered audio | ✓ FLOWING |
| render_corpus.py | call.wav file | render_call_wav → soundfile.write | Yes — actual wav file written to disk (live) | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| torch+dawdreamer coexist | `import torch, dawdreamer` | RenderEngine present, torch 2.12.0 | ✓ PASS |
| Determinism bit-identical | `np.array_equal(render(p,n), render(p,n))` | True | ✓ PASS |
| No clip | `np.max(np.abs(audio))` | 0.8900 == TARGET_PEAK | ✓ PASS |
| Mel contract | `MelExtractor()(wav, dir).shape` | (96,128) float32 | ✓ PASS |
| 3 distinct algorithms | unique dsp_string count | 3 | ✓ PASS |
| render_corpus valid pair | `render_corpus /tmp/rcorp` | "OK: rendered 1 call.wav", exit 0, file present | ✓ PASS |
| render_corpus bad manifest | bad spec_version | "RENDER FAILED: [.../000] spec_version '9.9' != '1.0'", exit 1 | ✓ PASS |
| Manifest validation | 2-ops/range/NaN/bool/gain | all raise IngestError | ✓ PASS |
| Full suite | `pytest -q` | 175 passed | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| DATA-06 | 06-01/02/03 | Deterministic headless FM render of call.wav from per-pair manifest, no Ableton, same engine at inference | ✓ SATISFIED | All 16 truths verified; live render + parity + determinism confirmed |
| DATA-01 | (reconciled) | Ableton/Operator authoring | ✓ SATISFIED (superseded) | Marked superseded-by-DATA-06 in REQUIREMENTS.md |
| DATA-02 | (reconciled) | Per-pair file layout | ✓ SATISFIED (superseded) | Updated to call.mid+call_fm.json+response.mid; call.wav derived |

No orphaned requirements: REQUIREMENTS.md maps DATA-06 to Phase 6 and it is claimed by all three plans.

### Anti-Patterns Found

None blocking. The benign `undefined symbol : effect` Faust poly-factory warning is emitted to stderr (visible in raw render calls) but is suppressed inside `render.py` via `contextlib.redirect_stderr` (T-06-10, cosmetic-only, documented). No TODO/FIXME/placeholder/stub patterns in the phase's source files. The `_OP_SLIDER_FIELDS = ("ratio","level")` narrowing (ADSR baked as Faust literals, not runtime sliders) is a documented, correct deviation (06-02-SUMMARY) — envelopes still take effect and are covered by the timbre-discriminability test.

### Human Verification Required

None. All success criteria are programmatically verifiable and were exercised live (dawdreamer present in `.venv`): determinism via `np.array_equal`, mel contract via shape/dtype assertion, parity via shared-function wiring, CLI via end-to-end run. No visual/UX/external-service surface in this phase.

### Gaps Summary

No gaps. All 6 ROADMAP success criteria and all 16 merged must-haves are verified in real code and confirmed by live execution. The phase goal — an owned, deterministic, headless FM renderer replacing the Ableton bounce, with train/serve parity through a single shared `render_call_wav` — is achieved. DATA-06 is satisfied; DATA-01/DATA-02 are reconciled as superseded. The existing 175-test suite is green with the 9 new synth-render tests and the migrated generate tests running (not skipping).

---

_Verified: 2026-06-02T10:20:00Z_
_Verifier: Claude (gsd-verifier)_

---
phase: 06-synth-independent-corpus-rendering
plan: 03
subsystem: inference
tags: [train-serve-parity, fm-synthesis, inference, generate, docs, requirements, gitignore]

# Dependency graph
requires:
  - phase: 06-synth-independent-corpus-rendering
    plan: 02
    provides: "render.py::render_call_wav (single shared render entrypoint with notes= passthrough), spec.py::SR, render_corpus CLI"
provides:
  - "apollo/scripts/generate.py — inference renders call.wav on-the-fly from call_fm.json via the shared render_call_wav (train/serve parity), reusing one parsed call_bpm/call_notes"
  - "data/pairs/CORPUS-CONVENTIONS.md — de-Ableton FM-manifest authoring guide (call_fm.json schema + render_corpus step)"
  - ".planning/REQUIREMENTS.md — DATA-01/02 reconciled as superseded by DATA-06; DATA-06 marked done"
  - ".gitignore — rendered data/pairs/**/call.wav ignored as a derived artifact"
affects: [DATA-05 corpus authoring (now unblocked against the FM-manifest workflow)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Inference and corpus rendering call ONE function (render_call_wav) — train/serve parity, no mel-distribution domain gap"
    - "Single MIDI parse shared between render and tokenize (call_bpm + call_notes passed through notes=) — never double-parse under differing tempo"
    - "Rendered array -> NamedTemporaryFile wav -> frozen MelExtractor (COND-01 path unchanged)"

key-files:
  created:
    - .planning/phases/06-synth-independent-corpus-rendering/06-03-SUMMARY.md
  modified:
    - apollo/scripts/generate.py
    - tests/test_generate.py
    - data/pairs/CORPUS-CONVENTIONS.md
    - .planning/REQUIREMENTS.md
    - .gitignore

key-decisions:
  - "Option A (render-only) implemented — the call.wav positional was REMOVED entirely, not demoted to an optional --call-wav override. generate.py always renders from call_fm.json. Rationale: the must_haves favor the manifest-render default, no existing caller in the repo passes a real call.wav (tests synthesized a mock), and a single code path is the cleanest parity guarantee. Option B's transitional override adds a divergent path the threat model (T-06-12) wants to avoid."
  - "Single-parse pitfall avoided: call_bpm = estimate_tempo() and call_notes = load_notes(..., tempo_bpm=call_bpm) are computed once, BEFORE the render; render_call_wav is called with call_bpm=call_bpm AND notes=call_notes so the MIDI is parsed exactly once. Verified by grep 'notes=call_notes'."
  - "IngestError (malformed call_fm.json / call.mid) is caught alongside FileNotFoundError and exits 1 (fail-loud, names the pair) — distinct from the generic exit-2 unexpected-error path."
  - "Rendered audio is written to a NamedTemporaryFile .wav at spec.SR, then fed to MelExtractor by path (MelExtractor takes a path, render returns an array). Mel step output (1,1,96,128) and all downstream sampling/decode/output-naming are unchanged."

requirements-completed: [DATA-06]

# Metrics
duration: ~12min
completed: 2026-06-02
---

# Phase 6 Plan 03: Inference Parity Wiring & Doc Reconciliation Summary

**`generate.py` now renders the inference call.wav on-the-fly from the per-pair `call_fm.json` via the same `render_call_wav` the corpus uses (train/serve parity, single shared MIDI parse), and the Ableton-bounce premise is removed from CORPUS-CONVENTIONS.md, REQUIREMENTS.md (DATA-01/02 superseded by DATA-06), and .gitignore.**

## Performance

- **Duration:** ~12 min
- **Tasks:** 2
- **Files modified:** 5 (1 created, 4 edited)

## Accomplishments

- **Train/serve parity wired (Task 1):** `generate.py` dropped the `call_wav` positional and now derives `<pair_dir>/call_fm.json`, rendering `call.wav` via `render_call_wav` — the identical engine + manifest format the corpus render uses. The mel step (temp-wav → frozen `MelExtractor` → `(1,1,96,128)`) and all response-side logic are unchanged.
- **Single-parse pitfall avoided:** `call_bpm` (`estimate_tempo`) and `call_notes` (`load_notes`) are computed once and both passed into `render_call_wav(..., call_bpm=call_bpm, notes=call_notes)`. The call MIDI is parsed exactly once and that one parse feeds both the renderer and the tokenizer — no second parse under a differing tempo assumption.
- **Option A chosen** (render-only; no `--call-wav` override) — see key-decisions. A single inference code path matches the threat model's parity intent (T-06-12) and there was no real caller to keep transitional.
- **Tests migrated (Task 1):** all four `generate.main([...])` invocations dropped the `call.wav` positional; the `mock_ckpt` fixture writes a valid `call_fm.json` (algorithm 0, exactly 3 in-range operators, gain 0.5) beside `call.mid`. The three render-exercising tests (smoke, output-valid, n-samples, temperature) are guarded with `pytest.importorskip("dawdreamer")`; the missing-call-mid test is unguarded (it exits before any render). The migrated tests drive the **real** `render_call_wav` — no stub/monkeypatch — for genuine parity coverage. All ran (dawdreamer present in `.venv`); full suite **175 passed**, no regression.
- **De-Ableton docs (Task 2):** `CORPUS-CONVENTIONS.md` rewritten — authored files are now `call.mid` + `call_fm.json` + `response.mid`; `call.wav` is a derived/gitignored render; the Ableton-bounce steps are replaced by the FM-manifest workflow + `render_corpus` step; the full `call_fm.json` schema (spec_version, algorithm 0–2, 3 operators with ranges, gain) is documented; the `call_fm.json` vs `apollo/eval/render_manifest.py` naming distinction is called out; the stale `venv/bin/python` paths are corrected to `.venv/bin/python` (no bare `venv/` remains).
- **Requirements reconciled (Task 2):** `DATA-01` and `DATA-02` carry an explicit "SUPERSEDED by DATA-06" note (IDs/checkboxes kept); `DATA-06` checkbox marked done and its traceability row updated to Phase 6 done.
- **gitignore (Task 2):** `data/pairs/**/call.wav` ignored (reproducible from `call_fm.json` + `call.mid`); authored `call.mid`/`call_fm.json`/`response.mid` stay tracked.

## Authored vs derived per-pair files (new convention)

| File | Status |
|---|---|
| `call.mid` | authored (tracked) |
| `call_fm.json` | authored (tracked) — hand-authored FM-parameter manifest |
| `response.mid` | authored (tracked) |
| `call.wav` | **derived** — rendered by `render_corpus` / `generate.py`, gitignored |

## Task Commits

1. **Task 1: render inference call.wav from call_fm.json via shared render_call_wav + migrate tests** — `782d00c` (feat)
2. **Task 2: de-Ableton corpus conventions + DATA-01/02 superseded-by-DATA-06 + gitignore** — `8de956c` (docs)

## Decisions Made

See key-decisions in frontmatter. Load-bearing: **Option A (render-only) — the call.wav positional is gone**, and the **single shared parse** (`notes=call_notes` + `call_bpm=call_bpm`) closes the double-parse pitfall.

## Deviations from Plan

None — plan executed as written. The plan permitted Option A or Option B; Option A (recommended) was chosen and the call.wav positional removed entirely.

**Note on a literal grep:** the plan's `! grep -q 'call.wav' tests/test_generate.py` check still matches because the `render_call_wav` function name contains `call_wav`, which the unescaped regex dot matches. No literal `call\.wav` (escaped-dot) and no `call.wav` positional argument remain in the test file — the criterion's intent (no supplied-wav positional) is fully satisfied; the only matches are the intentional `render_call_wav` function references the migrated tests are supposed to exercise.

## Threat Surface

No new surface beyond the plan's `<threat_model>`. Mitigations implemented:
- **T-06-11 / T-06-13 (Tampering / DoS):** inference renders through the same `render_call_wav` → `load_manifest` validation + `MAX_RENDER_SECONDS` cap as the corpus; no separate unvalidated inference render path; a crafted manifest cannot request an unbounded render.
- **T-06-12 (Spoofing/Tampering — parity):** one shared render function + single MIDI parse (call_bpm/call_notes reused) prevents a mel-distribution gap between training and inference.
- **T-06-14 (Info Disclosure — accept):** docs describe local authoring only; no secrets.

## Self-Check: PASSED

- `apollo/scripts/generate.py` — FOUND (contains `render_call_wav`, `call_fm.json`, `notes=call_notes`)
- `tests/test_generate.py` — FOUND (contains `call_fm.json`, `importorskip("dawdreamer")`, no `call.wav` positional)
- `data/pairs/CORPUS-CONVENTIONS.md` — FOUND (contains `call_fm.json`, `render_corpus`, `spec_version`, `render_manifest` distinction; no bounce step; `.venv/bin/python`)
- `.planning/REQUIREMENTS.md` — FOUND (DATA-06 done, DATA-01/02 superseded)
- `.gitignore` — FOUND (`data/pairs/**/call.wav`)
- Commit `782d00c` — FOUND
- Commit `8de956c` — FOUND
- Full suite: `.venv/bin/python -m pytest -q` → 175 passed

---
*Phase: 06-synth-independent-corpus-rendering*
*Completed: 2026-06-02*

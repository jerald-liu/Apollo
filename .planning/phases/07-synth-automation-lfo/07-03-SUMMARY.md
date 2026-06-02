---
phase: 07-synth-automation-lfo
plan: 03
subsystem: corpus-conventions
tags: [docs, lfo, spec-versioning, corpus-authoring, phase5-parity]

# Dependency graph
requires:
  - phase: 07-synth-automation-lfo
    provides: "FM spec v1.1 — optional global LFO (rate/depth/wave/target) on FmParams.lfo; manifest {1.0,1.1} loader with lfo-requires-1.1; tremolo/vibrato dsp_string math (50-cent vibrato literal)"
provides:
  - "Hand-authorable v1.1 lfo schema doc in data/pairs/CORPUS-CONVENTIONS.md (optional lfo JSON block + 4 field rows)"
  - "Documented {1.0,1.1} version rule + lfo-requires-1.1 in the schema field table"
  - "Phase-5 browser-synth parity formulas: tremolo lvl_mod = 1 - depth*(1-unipolar); vibrato pitch_mul = pow(2, lfo_bi*depth*50/1200)"
affects: [05-browser-synth, 03-corpus-inference]

tech-stack:
  added: []
  patterns:
    - "Documentation pinned to enforced validator values (T-07-09 doc-drift mitigation): documented ranges/enums match manifest.py LFO_* constants and spec.py enums exactly"

key-files:
  created: []
  modified:
    - data/pairs/CORPUS-CONVENTIONS.md

key-decisions:
  - "JSON example shown as a SEPARATE fenced `jsonc` block below the strict-JSON example (the main example stays strict JSON; the v1.1 extension carries comments and a note to drop them on disk)"
  - "Documented vibrato max-cents = 50 (confirmed against the 50.0 baked Faust literal in spec.py line 242 / 07-01-SUMMARY); noted discuss-phase could refine to 100"

requirements-completed: [SYNTH-01]

# Metrics
duration: ~10min
completed: 2026-06-02
---

# Phase 7 Plan 03: CORPUS-CONVENTIONS v1.1 LFO Doc Summary

**Extended `data/pairs/CORPUS-CONVENTIONS.md` so the optional v1.1 `lfo` block is hand-authorable from the doc alone (JSON example + four field rows + {1.0,1.1}/lfo-requires-1.1 version rule) and so Phase 5's browser synth can mirror the exact tremolo/vibrato math — every documented value verified against `apollo/synth/spec.py` and `manifest.py`.**

## Performance

- **Duration:** ~10 min
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- Schema heading updated `(spec_version "1.0")` → `(spec_version "1.0" or "1.1")`.
- `spec_version` field-table row rewritten: accepts `"1.0"` **or** `"1.1"`; any other value → `IngestError`; an `lfo` block **requires** `"1.1"` (a `"1.0"` manifest carrying `lfo` is rejected); v1.0 manifests still render bit-identically.
- Added an optional `lfo` block as a separate `jsonc` example below the strict-JSON example, introduced as the v1.1 extension (omit ⇒ static, Phase-6-identical).
- Added four field-table rows: `lfo` (object, optional v1.1), `lfo.rate` `0.05 .. 20.0` Hz, `lfo.depth` `0.0 .. 1.0`, `lfo.wave` `{0,1,2}` = sine/triangle/square (3=saw reserved), `lfo.target` `{0,1}` = level(tremolo)/pitch(vibrato) (2=FM-mod-depth reserved).
- Added an **LFO (v1.1) — synth modulation** subsection documenting: one global LFO applied to all carriers uniformly; the Phase-5 parity math (`lfo_bi ∈ [-1,1]`, `lfo_uni = (lfo_bi+1)/2`, tremolo `lvl_mod = 1 - depth*(1-lfo_uni)`, vibrato `pitch_mul = pow(2, (lfo_bi*depth*50)/1200)` with the explicit 50-cent default); the per-note phase reset (deterministic, onset-relative); and the low-rate partial-sweep behavior.

## Value verification (against source — T-07-09 doc-drift mitigation)

Every documented value was cross-checked against the actual 07-01 implementation:

| Documented | Source | Match |
|---|---|---|
| `spec_version ∈ {"1.0","1.1"}` | `manifest.py` `SUPPORTED_VERSIONS = {"1.0","1.1"}` (line 57) | ✓ |
| lfo requires "1.1" | `manifest.py` `"lfo block requires spec_version '1.1'"` (line 184) | ✓ |
| rate `[0.05, 20.0]` | `manifest.py` `LFO_RATE_MIN, LFO_RATE_MAX = 0.05, 20.0` (line 76) | ✓ |
| depth `[0.0, 1.0]` | `manifest.py` `LFO_DEPTH_MIN, LFO_DEPTH_MAX = 0.0, 1.0` (line 77) | ✓ |
| wave `{0,1,2}` sine/triangle/square | `spec.py` `LfoWave` SINE=0/TRIANGLE=1/SQUARE=2 (saw=3 reserved) | ✓ |
| target `{0,1}` level/pitch | `spec.py` `LfoTarget` LEVEL=0/PITCH=1 (FM-mod-depth=2 reserved) | ✓ |
| tremolo `lvl_mod = 1 - depth*(1-lfo_uni)` | `spec.py` line 233 `lvl_mod = 1.0 - lfo_depth * (1.0 - lfo_uni)` | ✓ |
| vibrato `pow(2, lfo_bi*depth*50/1200)` | `spec.py` line 242 `pitch_mul = pow(2.0, (lfo_bi * lfo_depth * 50.0) / 1200.0)` | ✓ |
| **vibrato max-cents = 50** | `spec.py` line 242 baked literal `50.0` (07-01-SUMMARY line 92) | ✓ |

- **Final vibrato max-cents documented:** `50` — matches the `50.0` literal that shipped in 07-01.
- **JSON example style:** separate fenced `jsonc` block (the main schema example remains strict JSON).
- **Ranges match manifest.py LFO_* constants:** confirmed (table above).

## Task Commits

1. **Task 1: document optional v1.1 lfo block + version rule + parity math** — `4579246` (docs)

## Files Created/Modified
- `data/pairs/CORPUS-CONVENTIONS.md` — schema heading, `spec_version` row, optional `lfo` jsonc example, four lfo field rows, **LFO (v1.1)** subsection. (134 lines total; rest of doc unchanged.)

## Deviations from Plan

None — plan executed exactly as written. (Operational note: `data/` is gitignored but `CORPUS-CONVENTIONS.md` is an explicitly tracked file, so the commit used `git add -f` on the single tracked path. No content deviation.)

## Self-Check: PASSED

- `data/pairs/CORPUS-CONVENTIONS.md` — FOUND; verify command prints `doc OK`; all acceptance greps pass (`spec_version "1.0" or "1.1"`, `lfo.rate`/`lfo.depth`/`lfo.wave`/`lfo.target`, `lvl_mod`, `pow(2`, `tremolo`, `vibrato`, `sine`, `square`, `50`).
- Commit `4579246` — present in git log.
- `git diff --name-only` (pre-commit) showed ONLY `data/pairs/CORPUS-CONVENTIONS.md` — no code/test files touched.

---
*Phase: 07-synth-automation-lfo*
*Completed: 2026-06-02*

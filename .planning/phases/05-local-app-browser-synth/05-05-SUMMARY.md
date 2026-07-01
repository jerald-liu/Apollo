---
phase: 05-local-app-browser-synth
plan: "05"
subsystem: app-registry-models
tags: [flask, registry, model-versioning, rollback, pin-pointer, append-only-log]
dependency_graph:
  requires: [05-01, 05-03, 05-04]
  provides: [run-registry, model-history-view, checkpoint-activate, active-pin]
  affects: [apollo/app/registry.py, apollo/app/app.py, apollo/app/jobs.py]
tech_stack:
  added: [registry.py (append-only runs.jsonl + ACTIVE pointer)]
  patterns: [membership-guard (T-05-17 mirrors _validate_pair_nnn), corpus-hash content-flag, pin-vs-retrain D-06]
key_files:
  created:
    - apollo/app/registry.py
    - apollo/app/templates/models.html
    - tests/test_app_registry.py
    - tests/test_app_models.py
  modified:
    - apollo/app/app.py
    - apollo/app/jobs.py
    - apollo/app/templates/dashboard.html
    - tests/test_app_ingest_train.py
decisions:
  - "registry is app-layer only — train.py/generate.py UNCHANGED; CLI training produces checkpoints but not registry rows (accepted v1 limitation)"
  - "_active_checkpoint: pin wins if file exists, stale pin falls to _latest_checkpoint, ACTIVE-unset == latest-by-mtime"
  - "corpus_hash is a content flag only (SEED-011 defers full snapshotting) — documented in registry.py module docstring"
  - "POST /models/activate validates against {r['checkpoint'] for r in list_runs()} BEFORE any set_active or path construction (T-05-17)"
  - "__latest__ as activate payload clears ACTIVE file (pin cleared, back to newest-by-mtime)"
  - "A completed run appended to runs.jsonl does NOT move ACTIVE — pin survives retrains (D-06)"
metrics:
  duration: "~6m"
  completed: "2026-06-04"
  tasks: 3
  files: 8
---

# Phase 5 Plan 05: Model Version-History + Rollback Summary

**One-liner:** Append-only run registry (models/runs.jsonl) with corpus_hash content-flag, ACTIVE pin pointer, /models view with per-run activate controls, and /generate resolution swapped to _active_checkpoint() so a pinned model survives subsequent retrains.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | registry.py + TrainingJob on_complete hook + registry tests | 2872bf5 | registry.py, jobs.py, app.py, test_app_registry.py |
| 2 | _active_checkpoint() + /generate call-site swap | 66c22ba | app.py |
| 3 | GET /models + POST /models/activate + models.html + dashboard link + models tests | 1e4e6db | app.py, models.html, dashboard.html, test_app_models.py, test_app_ingest_train.py |

## What Was Built

### apollo/app/registry.py (Task 1)
New module (174 lines). Append-only run registry written exclusively by the app layer:

- `runs_path(models_dir)` / `active_path(models_dir)`: path helpers
- `compute_corpus_hash(pairs_root)`: deterministic sha256 over qualifying pair dirs (3-digit names with call.mid + call_fm.json), sorted, feeding name:filename:file-sha256 tuples for each of {call.mid, call_fm.json, response.mid (if present)}. Content flag only — SEED-011 caveat documented.
- `append_run(models_dir, *, checkpoint, iteration, corpus_pair_count, corpus_hash, held_loss, train_loss, timestamp)`: stores checkpoint as basename only; thread-safe with module-level `_lock`; never moves ACTIVE.
- `list_runs(models_dir)`: returns rows newest-first; tolerates corrupt lines (defensive skip).
- `get_active` / `set_active` / `clear_active`: ACTIVE pointer round-trip.

### apollo/app/jobs.py (Task 1)
`TrainingJob.start()` extended with `on_complete=None` kwarg. `_read_stdout` calls `on_complete(train_loss, held_loss)` after `ret == 0`, wrapped in `try/except Exception` (registry failure never crashes the training thread, logged to stderr).

### apollo/app/app.py (Tasks 1, 2, 3)
- `_launch_training()`: inner closure that snapshots `corpus_hash` + `pair_count` at call time (D-06 race-safety); builds `_on_complete` closure calling `registry.append_run`; wires both `/train` and debounced auto-retrain call sites.
- `_active_checkpoint()`: pin-vs-auto-retrain resolver (D-06); stale pin falls through to `_latest_checkpoint()`.
- `/generate` call site swapped from `_latest_checkpoint()` to `_active_checkpoint()`.
- `GET /models`: renders run history with `effective_active` badge.
- `POST /models/activate`: registry membership guard (`{r["checkpoint"] for r in list_runs()}`) before any `set_active`; `__latest__` clears pin; unknown basenames → 400.

### models.html (Task 3)
Extends base.html. Worklist of run rows: checkpoint basename + timestamp + iteration + pair count + held_loss. `data-active` badge on effective-active row. Per-row "Use this one" button + "Use latest" button. Inline JS fetch handler reloads on success.

### dashboard.html (Task 3)
"Model history" link added to Generate tile.

### Tests
- `tests/test_app_registry.py`: 8 tests — append/list ordering, basename storage, corpus hash determinism + mutation, active pointer roundtrip, corrupt-line tolerance, empty corpus, invalid-pair exclusion.
- `tests/test_app_models.py`: 6 tests — empty state, run listing with badge, activate pin, `test_activate_rejects_unknown_checkpoint` (traversal + unregistered → 400, no ACTIVE write), back-to-latest, `test_pin_survives_new_run`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Existing test stub incompatible with new on_complete kwarg**
- **Found during:** Task 3 full suite run
- **Issue:** `test_train_starts_and_status` in `test_app_ingest_train.py` had `fake_start(self, pairs_root, epochs, output_dir)` — no `on_complete` kwarg. After `_launch_training()` started passing `on_complete=`, the stub raised `TypeError`.
- **Fix:** Added `on_complete=None` to the stub signature.
- **Files modified:** `tests/test_app_ingest_train.py`
- **Commit:** 1e4e6db (included in Task 3 commit)

## Known Stubs

None. The registry writes real JSON rows; the activate route validates against real list_runs(); models.html renders real template data; no hardcoded placeholder values flow to the UI.

## Threat Flags

All threats from the plan's threat register were mitigated:

| Flag | File | Description |
|------|------|-------------|
| T-05-17 mitigated | apollo/app/app.py::models_activate | Membership guard `{r["checkpoint"] for r in list_runs()}` before any set_active or path use; unregistered → 400. Asserted by test_activate_rejects_unknown_checkpoint. |
| T-05-18 mitigated | apollo/app/app.py::_active_checkpoint | Builds `Path("models") / name` only after T-05-17 validates the basename; stale pin falls back to latest; generate.py receives server-resolved path in fixed argv (no user strings). |
| T-05-19 accepted | apollo/app/registry.py::append_run | Server-side only writes; corrupt lines skipped on read; local single-user tool. |
| T-05-20 accepted | models/runs.jsonl | Local 127.0.0.1 only; no secrets; corpus_hash is one-way sha256. |

## Self-Check: PASSED

Files verified present:
- apollo/app/registry.py: FOUND
- apollo/app/templates/models.html: FOUND
- tests/test_app_registry.py: FOUND
- tests/test_app_models.py: FOUND

Commits verified:
- 2872bf5 (Task 1): FOUND
- 66c22ba (Task 2): FOUND
- 1e4e6db (Task 3): FOUND

Scripts unchanged:
- apollo/scripts/train.py: no diff
- apollo/scripts/generate.py: no diff

Test results: 247 passed, 1 deselected (slow) — all green.

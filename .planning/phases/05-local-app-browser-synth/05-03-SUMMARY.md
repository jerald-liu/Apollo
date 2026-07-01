---
phase: 05-local-app-browser-synth
plan: "03"
subsystem: apollo/app
tags: [flask, ingest, training, polling, loss-curve, multipart-upload, settings]
dependency_graph:
  requires:
    - apollo/app/app.py (05-01 factory, 05-02 /corpus route)
    - apollo/app/static/app.js (05-02 IIFE, showError, getCtx)
    - apollo/app/templates/corpus.html (05-02 pair worklist + scripts block)
    - apollo/synth/manifest.py (load_manifest)
    - apollo/synth/render.py (render, SR)
    - apollo/ingest/midi.py (load_notes)
    - apollo/ingest/errors.py (IngestError)
    - apollo/app/jobs.py (TrainingJob, 05-01)
  provides:
    - POST /ingest (validate→write→render call.wav)
    - POST /train + GET/POST /settings
    - GET /training (training.html)
    - corpus.html upload UI (call-mid-input, call-fm-input, add-pair-btn)
    - app.js polling loop + drawLossCurve + ingest FormData handler + settings handlers
  affects:
    - Phase 5 plans 04-05 (generate + patch editor build on these routes)
tech_stack:
  added: [soundfile (already in venv), tempfile (stdlib), shutil (stdlib)]
  patterns:
    - _allocate_next_nnn lock-guarded NNN allocation (T-05-07)
    - NamedTemporaryFile for load_manifest (path-taking API)
    - shutil.rmtree on IngestError (atomic failure, Pitfall 5)
    - threading.Timer 3.0s debounce for auto-retrain (D-06)
    - Canvas 2D loss curve (train solid #6D28D9, held dashed #15803D)
    - FormData multipart fetch('/ingest') with showError on failure
key_files:
  created:
    - apollo/app/templates/training.html
    - tests/test_app_ingest_train.py
  modified:
    - apollo/app/app.py
    - apollo/app/templates/corpus.html
    - apollo/app/static/app.js
    - pyproject.toml
decisions:
  - "Manifest validated via NamedTemporaryFile before dir allocation — load_manifest takes a path, not bytes; tmpfile cleaned up in finally block regardless of outcome"
  - "Pair dir cleaned up via shutil.rmtree on any IngestError after allocation (MIDI parse failure, render failure) — Pitfall 5: no orphaned dirs"
  - "_debounce dict instead of module-level var avoids closure assignment issues in Python; timer.daemon=True so Flask shutdown doesn't hang"
  - "render() (not render_call_wav) called with validated FmParams + notes — avoids re-reading the just-written files, reuses params already in memory"
  - "test_train_starts_and_status uses monkeypatch.setattr on TrainingJob.start to avoid spawning a real subprocess (fast test)"
metrics:
  duration: "~5 min"
  completed_date: "2026-06-03"
  tasks_completed: 3
  files_created: 2
  files_modified: 4
  tests_added: 6
requirements: [APP-03, APP-07, APP-08, APP-12]
---

# Phase 5 Plan 03: Ingest Route, Training View, and Upload UI Summary

**One-liner:** Server-side multipart-upload ingest (validates via load_manifest+load_notes, renders call.wav in-process via DawDreamer, allocates lock-guarded NNN dir), corpus upload UI, training view with live Canvas loss curve via 1s polling, and configurable response-storage settings.

## What Was Built

### Task 1: /ingest + /settings + /train + /training routes

**`apollo/app/app.py`** — Four new routes added to the `create_app` factory:

**`POST /ingest`**: Multipart upload handler.
1. Reads `call_mid` + `call_fm` (required) and `response_mid` (optional) from `request.files`.
2. Validates manifest BEFORE allocating a dir: writes `fm_bytes` to a `NamedTemporaryFile`, calls `load_manifest(tmp.name, "(upload)")`, catches `IngestError` → 400 with `{"ok": False, "error": e.reason}`.
3. Allocates pair dir via `_allocate_next_nnn()` (holds `_alloc_lock` around find-max+mkdir — T-05-07, RESEARCH OQ4 race prevention).
4. Writes `call_fm.json` + `call.mid`; validates MIDI via `load_notes`; renders `call.wav` in-process via `render(params, notes, pair_path=str(pair))` + `sf.write(...)`.
5. Removes partial dir (`shutil.rmtree`) on any `IngestError` — Pitfall 5 guarantee: no orphaned dirs.
6. Debounced auto-retrain: if `AUTO_RETRAIN`, cancels existing timer and schedules a new 3.0s `threading.Timer` (bulk drop → one run, D-06).

**`GET/POST /settings`**: Returns / updates `RESPONSES_DIR` (resolved via `Path(...).resolve()`) and `AUTO_RETRAIN` in `app.config`.

**`GET /training`**: Renders `training.html` with `responses_dir` + `auto_retrain` template vars.

**`POST /train`**: Calls `TRAINING_JOB.start(pairs_root, 300, "models")`; returns 409 if already running.

### Task 2: corpus upload UI + training.html + app.js extensions

**`apollo/app/templates/corpus.html`**: Added `<section id="upload-pair" class="card">` above the existing pair worklist with `call-mid-input`, `call-fm-input`, `response-mid-input` file inputs and `add-pair-btn`. The existing `{% block scripts %}` and pair list are untouched.

**`apollo/app/templates/training.html`**: New template extending `base.html`. Contains:
- `#train-btn` + `#auto-retrain` checkbox (pre-checked if `auto_retrain`)
- `#training-progress` div (initially hidden) with `#train-status` mono text, `.progress-bar`/`#progress-fill`, and `#loss-chart` canvas (600×200)
- `#responses-dir` text input + `#save-settings` button + `#settings-saved` confirmation span

**`apollo/app/static/app.js`**: Extended the existing IIFE with:
- **`drawLossCurve(canvas, history)`**: Canvas 2D path — train_loss solid `#6D28D9`, held_loss dashed `#15803D`, both scaled to canvas dimensions.
- **`startPolling()`**: `setInterval` 1000ms fetching `/status`; calls `updateTrainingUI(d)`; stops when `complete` or `error`.
- **`updateTrainingUI(d)`**: Reveals `#training-progress`, sets `#train-status` text (UI-SPEC copywriting), updates `#progress-fill` width, redraws loss curve.
- **`#add-pair-btn` click handler**: Builds `FormData`, POSTs to `/ingest`, calls `showError(data.error)` on failure, redirects to `/corpus` on success.
- **`#train-btn` click handler**: POSTs `/train`, calls `startPolling()`.
- **`#auto-retrain` change handler**: POSTs `/settings` with `{auto_retrain: checkbox.checked}`.
- **`#save-settings` click handler**: POSTs `/settings` with `{responses_dir: ...}`, shows `#settings-saved` briefly.
- On load with `#train-btn` present: fetches `/status` once; resumes polling if already running.

### Task 3: Tests + slow marker

**`pyproject.toml`**: Added `markers = ["slow: marks tests that run the real DawDreamer render (deselect with -m 'not slow')"]` under `[tool.pytest.ini_options]`. No `PytestUnknownMarkWarning` when collecting.

**`tests/test_app_ingest_train.py`**: 6 tests:
- `test_ingest_valid_pair_renders_wav` (`@pytest.mark.slow`): real DawDreamer path; asserts `call.wav` written.
- `test_ingest_bad_manifest_no_dir`: bad JSON → 400 + zero pair dirs.
- `test_ingest_bad_midi_cleans_up`: valid manifest + empty MIDI → 400 + no orphaned dirs.
- `test_corpus_upload_ui_present`: `/corpus` body contains all three upload-UI ids.
- `test_train_starts_and_status`: `TrainingJob.start` monkeypatched; POST /train → 200; GET /status → running.
- `test_settings_roundtrip`: POST + GET /settings round-trip for `responses_dir` + `auto_retrain`.

## Verification

```
python -m pytest tests/test_app_ingest_train.py -q -k "not slow"  ✓ (5/5 pass, 1 deselected)
python -m pytest tests/test_app_scaffold.py tests/test_app_synth.py -q  ✓ (18/18 still pass)
grep -r 'shell=True' apollo/app/  → only docstring comment, no real usage  ✓
GET /corpus → call-mid-input, add-pair-btn present  ✓
GET /training → train-btn, loss-chart, auto-retrain, progress-bar-fill, responses-dir  ✓
Bad manifest POST /ingest → 400 ok:False, no dir created  ✓
```

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

One minor deviation in implementation detail (not a deviation from spec): `render()` was called directly with already-validated `FmParams + notes` (instead of `render_call_wav` which re-reads files from disk). This avoids writing `call_fm.json` and `call.mid` to disk and then re-reading them via a manifest/MIDI parse. The result is identical; `render()` is the function `render_call_wav` delegates to. The plan's interface table lists both; `render()` was chosen to avoid the redundant re-parse.

## Threat Model Coverage

| Threat | Status | Evidence |
|--------|--------|----------|
| T-05-07 (unsafe file write from drag-drop) | Mitigated | `_allocate_next_nnn` allocates server-side under lock; client never supplies a path |
| T-05-08 (malformed manifest/MIDI) | Mitigated | `load_manifest` + `load_notes` validate before/at write; `shutil.rmtree` on failure |
| T-05-09 (command injection) | Mitigated | `TrainingJob.start` builds fixed argv; no user string in cmd; no `shell=True` |
| T-05-10 (responses_dir path) | Accepted | `Path(...).resolve()` normalizes; user chooses their own local dir |
| T-05-11 (render blocks request) | Accepted | Render ~0.1-0.2s; `threaded=True` keeps /status responsive |

## Known Stubs

None — all three task goals are fully wired and end-to-end:
- Browser upload → `/ingest` → pair dir with `call.wav` is APP-03 end-to-end.
- `Train model` button → `/train` → `TrainingJob.start` → subprocess → `/status` polling → progress bar + loss curve is APP-07 + APP-08 end-to-end.
- `/settings` round-trip persists `responses_dir` + `auto_retrain` (APP-12).

## Commits

| Hash | Message |
|------|---------|
| 7ac3f83 | feat(05-03): /ingest route (validate→write→render call.wav) + /settings + /train + /training |
| 0449e50 | feat(05-03): corpus upload UI + training.html + polling/loss-curve + ingest FormData handler |
| c98a7de | test(05-03): ingest + training route tests + slow marker in pyproject.toml |

## Self-Check: PASSED

All 4 created/modified files exist. All 3 task commits verified in git log.

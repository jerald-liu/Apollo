---
phase: 05-local-app-browser-synth
plan: "01"
subsystem: apollo/app
tags: [flask, scaffold, training-job, dashboard, css-tokens, spec-constants]
dependency_graph:
  requires: [apollo/ingest/midi.py, apollo/ingest/errors.py, apollo/synth/manifest.py, apollo/synth/spec.py]
  provides: [apollo/app (package), create_app factory, TrainingJob, /status /midi /audio / routes, spec_constants.js]
  affects: [Phase 5 plans 02-05 (all build on this scaffold)]
tech_stack:
  added: [Flask (already in venv), threading, subprocess.Popen, Jinja2 templates]
  patterns: [create_app factory (mirroring eval/web/app.py), _validate_pair_nnn traversal guard, TrainingJob daemon thread, CSS token inheritance]
key_files:
  created:
    - apollo/app/__init__.py
    - apollo/app/__main__.py
    - apollo/app/app.py
    - apollo/app/jobs.py
    - apollo/app/static/style.css
    - apollo/app/static/spec_constants.js
    - apollo/app/templates/base.html
    - apollo/app/templates/dashboard.html
    - tests/test_app_scaffold.py
  modified: []
decisions:
  - "_known_pairs_set scans for call.mid+call_fm.json presence (NOT discover_pairs) — call.wav is a derived artifact rendered after ingest (RESEARCH Pitfall 5)"
  - "host=127.0.0.1 lives only in __main__.py; create_app factory never binds (mirrors eval/web/app.py pattern)"
  - "TrainingJob uses subprocess.Popen+daemon thread+line iteration; never communicate() to preserve real-time progress"
  - "spec_constants.js bounds copied verbatim from manifest.py; dual client+server validation pattern"
metrics:
  duration: "~20 min"
  completed_date: "2026-06-03"
  tasks_completed: 3
  files_created: 9
  tests_added: 5
requirements: [APP-01, APP-02]
---

# Phase 5 Plan 01: Flask App Scaffold Summary

**One-liner:** Local-only Flask app shell with `python -m apollo.app` launcher, `create_app` factory, traversal-guarded routes (/status /midi /audio /), `TrainingJob` state holder, 3-tile dashboard, CSS token extension, and spec_constants.js bounds mirroring manifest.py verbatim.

## What Was Built

### Task 1: Flask scaffold — package, launcher, factory, TrainingJob

**`apollo/app/__init__.py`** — package marker.

**`apollo/app/jobs.py`** — `TrainingJob` state holder. Wraps `subprocess.Popen` in a daemon thread that reads stdout line-by-line (never `communicate()`). Parses train.py's verified stdout format `epoch {E}/{N}  train_loss={X:.4f}  held_loss={Y:.4f}` via compiled regex. Thread-safe snapshot via `threading.Lock`. Status transitions: `idle → running → (complete | error)`.

**`apollo/app/app.py`** — `create_app(pairs_root="data/pairs") -> Flask`. Mirrors `apollo/eval/web/app.py`:
- `PAIRS_ROOT` always resolved to absolute path (Flask send_file pitfall)
- `_known_pairs_set()` scans for `call.mid + call_fm.json` presence (NOT `discover_pairs`)
- `_validate_pair_nnn(nnn)` aborts 404 if nnn not in known set — T-05-01 traversal guard
- Routes: `GET /` (dashboard), `GET /audio/<nnn>/<filename>` (call.wav only), `GET /midi/<nnn>/<filename>` (call.mid|response.mid, note JSON via load_notes), `GET /status` (TrainingJob snapshot)

**`apollo/app/__main__.py`** — one-command launch. Binds `127.0.0.1` only (never 0.0.0.0), `debug=False`, `threaded=True` (concurrent /status polling during training). Opens browser via `threading.Timer(0.5, webbrowser.open)`.

### Task 2: Dashboard templates, CSS tokens, and spec_constants.js

**`apollo/app/static/style.css`** — Full `:root` token block copied from `eval/web/static/style.css`, then `--accent: #6D28D9` (UI-SPEC purple override), `--2xl: 48px`, `--3xl: 64px` added. All eval component classes preserved. New Phase 5 rules: `.tile-grid`, `.tile`, `.display` (40px mono), `.heading`, `.trust-badge`, `.progress-bar`, `.status-dot`, `.op-panel`, `.loss-chart-wrap`.

**`apollo/app/static/spec_constants.js`** — `SPEC_VERSION = "1.1"`, `N_OPERATORS = 3`, `ALGORITHMS` (STACK/PARALLEL_MODS/CARRIER_PAIR), `BOUNDS` (verbatim from manifest.py: ratio [0.5,12.0], lfo_rate [0.05,20.0], etc.), `LFO_WAVES`, `LFO_TARGETS`, `checkBounds()` function mirroring `_check_number`.

**`apollo/app/templates/base.html`** — shared layout with persistent trust badge "Runs on your machine — nothing is uploaded", nav links, `url_for` static refs, content + scripts blocks.

**`apollo/app/templates/dashboard.html`** — 3-tile grid: Corpus (pair count at `.display` size, progress bar, empty-state guard), Training (status dot + link), Generate (link). Loads `spec_constants.js`.

### Task 3: Scaffold smoke tests

**`tests/test_app_scaffold.py`** — 5 tests using `tmp_path` pairs_root fixture with `007/` containing `call.mid + call_fm.json` (no `call.wav` — verifies Pitfall 5 mitigation):
- `test_dashboard_renders`: GET / → 200, body contains `trust-badge`
- `test_status_idle`: GET /status → `status=="idle"`, `epoch==0`
- `test_known_pair_enumerated`: pair counted despite absent call.wav
- `test_unknown_nnn_404`: `/midi/999/call.mid` and `/midi/../etc/call.mid` → 404
- `test_audio_bad_filename_400`: `/audio/007/secrets.txt` → 400

## Verification

```
python -m apollo.app --help  ✓ (exits 0)
python -m pytest tests/test_app_scaffold.py -q  ✓ (5/5 passed)
GET /status → {"status": "idle", "epoch": 0, ...}  ✓
GET /midi/zzz/call.mid → 404  ✓
host="127.0.0.1" in __main__.py, no 0.0.0.0  ✓
```

## Deviations from Plan

None — plan executed exactly as written.

The only pre-existing test failure (`test_lfo_pitch_depth0_matches_static` in `test_synth_render.py` for CARRIER_PAIR algorithm) is unrelated to this plan and was already failing before execution. Logged to deferred-items.

## Threat Model Coverage

| Threat | Status | Evidence |
|--------|--------|----------|
| T-05-01 (path traversal /midi, /audio) | Mitigated | `_validate_pair_nnn` enumeration guard + filename allow-list; test_unknown_nnn_404 asserts 404 for traversal attempt |
| T-05-02 (server binding) | Mitigated | `host="127.0.0.1"`, `debug=False` in __main__.py; grep-verified in acceptance criteria |
| T-05-03 (DoS via load_notes) | Accepted | load_notes already caps at MAX_NOTES_PER_PAIR=1000 (Phase 1) |

## Commits

| Hash | Message |
|------|---------|
| 21057f7 | feat(05-01): Flask scaffold — package, launcher, factory, TrainingJob |
| d5ab0ef | feat(05-01): dashboard templates, CSS tokens, and spec_constants.js |
| 88597b7 | test(05-01): scaffold smoke tests — pair enumeration, idle status, traversal |

## Known Stubs

- Training tile shows static "Not trained" status — status-dot JS polling not wired (Plan 05-03 scope)
- `/corpus`, `/training`, `/generate` links in nav return 404 — stub routes added in Plans 05-02, 05-03, 05-04

These are intentional stub links; the dashboard tile CTAs point to routes that don't exist yet. They are not wired stubs for this plan's goals (APP-01, APP-02), which are satisfied: the app launches, dashboard renders 3 tiles + trust badge, /status returns idle, routes are traversal-guarded.

## Self-Check: PASSED

All 9 files created, all 3 task commits verified in git log.

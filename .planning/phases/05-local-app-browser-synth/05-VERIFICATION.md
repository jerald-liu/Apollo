---
phase: 05-local-app-browser-synth
verified: 2026-06-03T00:00:00Z
status: human_needed
score: 15/15 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Navigate to http://127.0.0.1:5001/ in a browser and interact with the corpus/generate/training tabs"
    expected: "All 3 tiles render at Display size; trust badge visible; navigation works between corpus, training, generate, models pages"
    why_human: "HTML rendering and layout fidelity require a real browser; automated checks confirm route responses but not visual correctness"
  - test: "On /corpus page, click 'Add pair', select a .mid and a call_fm.json, click 'Add pair' button"
    expected: "Upload succeeds; page refreshes with new pair listed; pair shows Play-call button; on error, IngestError reason shown inline"
    why_human: "File-picker drag-drop interaction and inline error display require a real browser session"
  - test: "On /corpus page, click 'Play call' button on a valid pair"
    expected: "Audio plays through browser speakers; FM timbre audible (not silence)"
    why_human: "Web Audio playback requires a real browser with audio output; cannot be verified programmatically"
  - test: "On /generate page, load a preset from the dropdown, edit a control (e.g. ratio slider), then click 'Preview note'"
    expected: "Synth produces a tone that changes as you edit; LFO toggle enables tremolo/vibrato; live preview fires on every control change (~150ms debounce)"
    why_human: "Real-time audio preview and live-preview-on-change require browser interaction with Web Audio"
  - test: "On /training page, click 'Train model'"
    expected: "Progress bar and epoch counter animate; loss curve plots both train and held loss lines in #6D28D9 and #15803D; 'Training complete' banner appears on finish"
    why_human: "Live polling UI and canvas loss curve rendering require a real browser running against a live server"
  - test: "On /models page (after at least one training run via the app), verify run history list shows timestamp/pairs/losses; click 'Use this one' on an older run; trigger a new training run; confirm the pin persists"
    expected: "Active badge moves to selected checkpoint; subsequent training does not move the pin; 'Use latest' clears it"
    why_human: "Requires a live training run to populate runs.jsonl; pin-survives-retrain is a stateful multi-step UX flow"
---

# Phase 5: Local App & In-Browser Synth — Verification Report

**Phase Goal:** A purely local, user-facing app that lets a user build a corpus by drag-and-drop, render call/response audio in-browser (no Ableton), trigger training, and upload a call to get a generated response back — closing the whole loop locally. Primary purpose: a public demonstration front-end showing Apollo trains/generates on-device with data never leaving the machine.
**Verified:** 2026-06-03
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | App binds 127.0.0.1, never 0.0.0.0, debug=False (SC#1) | VERIFIED | `__main__.py:48` `app.run(host="127.0.0.1", port=args.port, debug=False, threaded=True)`; grep for 0.0.0.0 in apollo/app/ returns nothing |
| 2 | Dashboard renders 3 tiles + trust badge (SC#1, APP-02) | VERIFIED | `templates/base.html` has `trust-badge` + "nothing is uploaded"; `templates/dashboard.html` has `.tile-grid` with 3 tiles; GET / → 200 + "trust-badge" confirmed by test |
| 3 | Drag-drop ingest end-to-end: corpus.html upload UI → /ingest → validated write → in-process call.wav render; IngestError inline on failure (SC#2, APP-03) | VERIFIED | `corpus.html:10-13` has `call-mid-input`, `call-fm-input`, `add-pair-btn`; `app.py:257-333` /ingest calls `load_manifest` + `load_notes` + in-process `render()` + `sf.write()`; `shutil.rmtree` on failure; test `test_ingest_bad_manifest_no_dir` asserts no orphan dir |
| 4 | Browser 3-op v1.1 FM synth: all 3 algorithms, op_level*freq mod scaling, LFO tremolo/vibrato per CORPUS-CONVENTIONS formulas, no Tone.js (SC#4, APP-05) | VERIFIED | `synth.js:287 lines`; `playNote`, `applyAdsr`, `attachLfo`, `playSequence` all present; tremolo `1 - depth*(1 - lfo_uni)` and vibrato `freq*depth*50/1200*Math.LN2` formulas present; no Tone.js reference; algorithm branches for STACK/PARALLEL_MODS/CARRIER_PAIR wired correctly |
| 5 | Patch editor: algorithm + per-op ratio/level/ADSR + collapsible LFO, client-validated via BOUNDS, serializes load_manifest-valid JSON (SC#4, APP-04) | VERIFIED | `editor.js:450 lines`; `buildEditor`, `readPatch`, `validatePatch`, `checkBounds`, `lfo-section`; 3 bundled presets pass `load_manifest` with algorithms 0/1/2 |
| 6 | Editing any editor control previews via browser synth (debounced ~150ms) (APP-06) | VERIFIED (code) / HUMAN for audio | `editor.js:431-433` debounce timer wraps `previewNote()`; `previewNote()` calls `ApolloSynth.playSequence`; code path confirmed. Actual audio playback requires human testing |
| 7 | Training triggers: manual Train button + debounced auto-retrain; POST /train subprocesses apollo.scripts.train; 300 epochs; 409 on already-running (SC#5, APP-07) | VERIFIED | `app.py:367-378` /train calls `_launch_training()`; `jobs.py:75-80` builds fixed argv `["python","-m","apollo.scripts.train", pairs_root, "--epochs","300", "--output-dir","models"]`; returns 409 if running; test `test_train_starts_and_status` passes |
| 8 | Live training UI: progress bar + loss canvas, ~1s polling of /status; drawLossCurve strokes train (#6D28D9) + held (#15803D) (SC#5, APP-08) | VERIFIED (code) / HUMAN for live rendering | `app.js:80-108` drawLossCurve; `app.js:123` setInterval 1000ms; `training.html` has `loss-chart`, `progress-bar-fill`, `train-btn`; colors confirmed; test `test_train_starts_and_status` passes. Live animated rendering requires human |
| 9 | Configurable response storage: POST /settings persists responses_dir; GET /settings echoes it (SC#6, APP-12) | VERIFIED | `app.py:335-356`; test `test_settings_roundtrip` passes; `RESPONSES_DIR` persists across the session |
| 10 | Call→response: POST /generate validates manifest, allocates pair dir, subprocesses generate.py with fixed argv, copies response to RESPONSES_DIR, auditions via call's own patch D-17 (SC#7, APP-09) | VERIFIED (code) / HUMAN for actual generation | `app.py:448-535`; fixed argv `["python","-m","apollo.scripts.generate", str(ckpt), str(pair/call.mid)]`; `shutil.copy2` into RESPONSES_DIR; `app.js:389-402` fetches /midi then `ApolloSynth.playSequence(getCtx(), patch, notes)` for D-17; test `test_generate_happy_path_stubbed` stubs subprocess and confirms copy |
| 11 | /midi returns note JSON; corpus play-call and response audition via same synth (APP-10, APP-11) | VERIFIED (code) / HUMAN for audio | `app.py:199-221` /midi with traversal guard + response_NNN.mid regex; `corpus.html:28` play-call button; `app.js:189-196` fetch /midi → `ApolloSynth.playSequence`; test `test_midi_notes_json` passes |
| 12 | 3 bundled presets covering algorithms 0/1/2 (APP-13) | VERIFIED | bright_bell.json (algorithm=0, no LFO), warm_pad.json (algorithm=1, tremolo LFO), vibrato_lead.json (algorithm=2, vibrato LFO); all pass `load_manifest` |
| 13 | Every completed training run appends a row to models/runs.jsonl with all required fields; list_runs returns newest-first; GET /models view (SC#8, APP-14) | VERIFIED | `registry.py` `append_run`, `list_runs`, `compute_corpus_hash`, `get_active`, `set_active`, `clear_active`; `jobs.py:123-128` on_complete callback invoked on ret==0, wrapped in try/except; `app.py:155-175` _on_complete closure; test suite passes |
| 14 | /generate resolves checkpoint via _active_checkpoint(): pin wins, stale pin falls back to latest (APP-15) | VERIFIED | `app.py:426-446` `_active_checkpoint()` with pin→stale→latest logic; `app.py:493` generate calls `_active_checkpoint()`; test `test_activate_pins_checkpoint` passes |
| 15 | POST /models/activate: registry-membership guard rejects unknown/traversal basenames; pin survives subsequent retrains; ACTIVE file never constructed from raw request before check (APP-15) | VERIFIED | `app.py:559-588` builds `known = {r["checkpoint"] for r in registry.list_runs(...)}` before any `set_active`; test `test_activate_rejects_unknown_checkpoint` asserts "../../etc/passwd" → 400; test `test_pin_survives_new_run` passes |

**Score:** 15/15 truths verified (6 require human testing for audio/live-UI aspects)

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `apollo/app/__main__.py` | One-command launcher: create_app + webbrowser.open + 127.0.0.1 bind | VERIFIED | 54 lines; webbrowser.Timer(0.5, ...), host="127.0.0.1", debug=False, threaded=True |
| `apollo/app/app.py` | create_app factory, all routes, _validate_pair_nnn guard | VERIFIED | 601 lines; all routes present; traversal guards in place |
| `apollo/app/jobs.py` | TrainingJob with on_complete hook | VERIFIED | 141 lines; on_complete called only on ret==0, wrapped in try/except |
| `apollo/app/registry.py` | Append-only run registry + corpus_hash + ACTIVE pointer | VERIFIED | 204 lines; all 6 functions present |
| `apollo/app/static/spec_constants.js` | JS bounds/enums mirrored from manifest.py + spec.py | VERIFIED | SPEC_VERSION="1.1", N_OPERATORS=3, BOUNDS with ratio:[0.5,12.0], lfo_rate:[0.05,20.0], checkBounds function |
| `apollo/app/static/synth.js` | 3-op v1.1 Web Audio FM engine | VERIFIED | 287 lines; all 3 algorithms; op_level*freq; LFO tremolo+vibrato; no Tone.js |
| `apollo/app/static/editor.js` | Patch editor: controls, validate, serialize | VERIFIED | 450 lines; buildEditor, readPatch, validatePatch, checkBounds, LFO section, live preview debounce |
| `apollo/app/static/app.js` | Audition wiring + ingest FormData + polling + generate handler | VERIFIED | 454 lines; all required fetch patterns present |
| `apollo/app/templates/base.html` | Trust badge + nav | VERIFIED | trust-badge, "nothing is uploaded" |
| `apollo/app/templates/dashboard.html` | 3-tile dashboard | VERIFIED | tile-grid, 3 tiles, /models link |
| `apollo/app/templates/corpus.html` | Upload UI + pair list + play-call buttons | VERIFIED | call-mid-input, call-fm-input, add-pair-btn, play-call |
| `apollo/app/templates/training.html` | Train button, auto-retrain toggle, progress bar, loss canvas | VERIFIED | train-btn, loss-chart, auto-retrain, progress-bar-fill, responses-dir |
| `apollo/app/templates/generate.html` | MIDI upload + patch editor + generate button + responses list | VERIFIED | patch-editor, generate-btn, "No responses generated yet" |
| `apollo/app/templates/models.html` | Run history table + active badge + "Use this one" | VERIFIED | "Use this one", data-active badge, empty-state copy |
| `apollo/app/presets/bright_bell.json` | algorithm=0, STACK, no LFO | VERIFIED | load_manifest validates cleanly |
| `apollo/app/presets/warm_pad.json` | algorithm=1, PARALLEL_MODS, tremolo LFO | VERIFIED | load_manifest validates; LfoParams(rate=0.3, depth=0.4, wave=0, target=0) |
| `apollo/app/presets/vibrato_lead.json` | algorithm=2, CARRIER_PAIR, vibrato LFO | VERIFIED | load_manifest validates; LfoParams(rate=5.0, depth=0.6, wave=0, target=1) |
| `tests/test_app_scaffold.py` | Scaffold smoke tests | VERIFIED | 5 tests pass |
| `tests/test_app_synth.py` | synth.js static checks + /corpus + /midi | VERIFIED | 4+ tests pass |
| `tests/test_app_ingest_train.py` | Ingest + training route tests | VERIFIED | Fast tests pass (slow DawDreamer test skipped) |
| `tests/test_app_generate.py` | Generate + presets + responses | VERIFIED | All tests pass |
| `tests/test_app_registry.py` | Registry functions | VERIFIED | 5 tests pass |
| `tests/test_app_models.py` | Models routes + activate security | VERIFIED | All tests pass |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `__main__.py` | `app.py::create_app` | import + `app.run(host="127.0.0.1", threaded=True)` | WIRED | Confirmed at line 48 |
| `/status` | `jobs.py::TrainingJob.snapshot` | `app.config["TRAINING_JOB"].snapshot()` | WIRED | `app.py:225` |
| `spec_constants.js` | `apollo/synth/manifest.py` constants | verbatim numeric copy | WIRED | BOUNDS values match; lfo_rate:[0.05,20.0] confirmed |
| `app.js` | `/midi/<nnn>/<file>` | fetch then `ApolloSynth.playSequence(notes, patch)` | WIRED | `app.js:189-196` |
| `synth.js` | `spec_constants.js (ALGORITHMS, LFO_TARGETS)` | numeric algorithm + lfo.target mapping | WIRED | `synth.js` uses ALGORITHMS branches |
| `/ingest` | `apollo.synth.load_manifest` + `apollo.synth.render.render` | in-process validation + canonical render | WIRED | `app.py:281,304` |
| `corpus.html upload UI` | `/ingest` | `app.js` multipart FormData `fetch('/ingest')` | WIRED | `app.js:220-225` |
| `/train` | `jobs.py::TrainingJob.start` | `_launch_training()` → `TRAINING_JOB.start(...)` | WIRED | `app.py:375` |
| `app.js polling` | `/status` | `setInterval` fetch ~1s + `drawLossCurve` | WIRED | `app.js:123,168` |
| `editor.js` | `spec_constants.js checkBounds/BOUNDS` | client-side validation before serialize | WIRED | `editor.js` uses `checkBounds`, `BOUNDS[` |
| `editor.js` | `ApolloSynth.playSequence` | live preview of edited patch | WIRED | `editor.js:432-433` |
| `/generate (POST)` | `apollo.scripts.generate (subprocess)` | fixed argv `["python","-m","apollo.scripts.generate",...]` | WIRED | `app.py:501-507` |
| `jobs.py::_read_stdout (completion)` | `registry.append_run` | `on_complete` callback invoked after subprocess exits 0 | WIRED | `jobs.py:123-128`; `app.py:155-174` |
| `/generate` | `_active_checkpoint()` | checkpoint resolution swap from `_latest_checkpoint` | WIRED | `app.py:493` |
| `/models/activate` | `registry.list_runs` | membership guard before writing ACTIVE | WIRED | `app.py:582-584` |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| `dashboard.html` | `n_pairs` | `_known_pairs_set()` scans PAIRS_ROOT | Yes — filesystem enumeration | FLOWING |
| `corpus.html` pair list | `pairs` (list of nnn + patch) | `_known_pairs_set()` + `json.loads(call_fm.json)` | Yes — reads actual files | FLOWING |
| `training.html` progress | `d.epoch / d.total_epochs / d.loss_history` | `/status` → `TrainingJob.snapshot()` → parsed stdout | Yes — real process stdout | FLOWING |
| `models.html` run table | `runs` | `registry.list_runs("models")` → `runs.jsonl` | Yes — reads registry file | FLOWING |
| `app.js` audition | `notes` | `/midi/<nnn>/<file>` → `load_notes()` | Yes — parses real MIDI files | FLOWING |

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Flask app imports cleanly | `.venv/bin/python -c "from apollo.app.app import create_app; a=create_app(); c=a.test_client(); print(c.get('/').status_code)"` | 200 | PASS |
| /status returns idle JSON | `.venv/bin/python -c "..."` (scaffold test) | `{"status":"idle", "epoch":0,...}` | PASS |
| /midi rejects unknown nnn | test_unknown_nnn_404 | 404 | PASS |
| /presets/bright_bell returns valid JSON | test_presets_listed_and_valid | 200 + JSON | PASS |
| /presets traversal rejected | test_preset_traversal_rejected | 400/404 | PASS |
| registry append + list_runs newest-first | test_append_and_list_newest_first | 2 rows, newest first | PASS |
| activate rejects traversal basename | test_activate_rejects_unknown_checkpoint | 400 | PASS |
| pin survives retrain | test_pin_survives_new_run | ACTIVE unchanged | PASS |
| Bad manifest /ingest → 400 + no orphan | test_ingest_bad_manifest_no_dir | 400, 0 dirs | PASS |

---

## Requirements Coverage

| Requirement | Plan | Description | Status | Evidence |
|-------------|------|-------------|--------|---------|
| APP-01 | 05-01 | One-command launch, 127.0.0.1, no 0.0.0.0 | SATISFIED | `__main__.py:48`; tests pass |
| APP-02 | 05-01 | Dashboard: 3 tiles, trust badge | SATISFIED | `dashboard.html`, `base.html`; test_dashboard_renders |
| APP-03 | 05-03 | Drag-drop ingest: validated write, in-process render, IngestError inline | SATISFIED | `app.py:/ingest`; test_ingest_bad_manifest_no_dir, test_corpus_upload_ui_present |
| APP-04 | 05-04 | Patch editor: algorithm + per-op + collapsible LFO, BOUNDS-validated | SATISFIED (code) | `editor.js`; 3 presets pass load_manifest |
| APP-05 | 05-02 | Browser 3-op v1.1 FM synth: algorithms, op_level*freq, LFO | SATISFIED (code) | `synth.js`; structure checks pass |
| APP-06 | 05-04 | Live preview on every control change (debounced) | SATISFIED (code) | `editor.js:431-433`; HUMAN for actual audio |
| APP-07 | 05-03 | Train triggers: manual + debounced auto, POST /train subprocesses train.py | SATISFIED | `app.py:/train`; `jobs.py`; test_train_starts_and_status |
| APP-08 | 05-03 | Progress bar + loss canvas + 1s polling | SATISFIED (code) | `app.js:drawLossCurve,setInterval`; `training.html`; HUMAN for live rendering |
| APP-09 | 05-04 | Call→response: /generate subprocesses generate.py, copies to store, D-17 audition | SATISFIED (code) | `app.py:/generate`; `app.js:389-402`; test_generate_happy_path_stubbed |
| APP-10 | 05-02 | /midi returns note JSON, played via browser synth | SATISFIED (code) | `app.py:199-221`; test_midi_notes_json; HUMAN for audio |
| APP-11 | 05-02 | Corpus pair audition via play-call button | SATISFIED (code) | `corpus.html:28`; `app.js:189-196`; HUMAN for audio |
| APP-12 | 05-03 | Configurable response storage + listing | SATISFIED | `app.py:/settings,/responses`; test_settings_roundtrip |
| APP-13 | 05-04 | 3 bundled presets, 3 algorithms | SATISFIED | bright_bell(0), warm_pad(1), vibrato_lead(2); all load_manifest-valid |
| APP-14 | 05-05 | Training run registry: runs.jsonl, corpus_hash, list_runs | SATISFIED | `registry.py`; `jobs.py:on_complete`; test_app_registry passes |
| APP-15 | 05-05 | /models view + activate + pin survives retrain + _active_checkpoint | SATISFIED | `app.py:/models,/models/activate`; `models.html`; test_app_models passes |

**All 15 APP requirements (APP-01 through APP-15) covered and satisfied.**

---

## ROADMAP Success Criteria Coverage

| SC | Description | Status | Key Evidence |
|----|-------------|--------|--------------|
| SC#1 | Local-only — app runs entirely on-device, no data leaves | SATISFIED | `__main__.py:48` host="127.0.0.1"; base.html trust badge; no outbound HTTP calls |
| SC#2 | Drag-and-drop pair ingest → valid data/pairs/NNN/ with inline errors | SATISFIED | /ingest route; load_manifest + load_notes validation; shutil.rmtree on failure |
| SC#3 | Corpus-growth flow — visible pair count vs 30 target, frictionless add-another loop | SATISFIED | dashboard.html pair count tile + progress bar; corpus.html Add pair section |
| SC#4 | In-browser FM synth (3-op v1.1 per D-20 override, not 4-op) + patch editor + live preview | SATISFIED (code) / HUMAN for audio | synth.js + editor.js + spec_constants.js; 3 presets validated; live preview debounced |
| SC#5 | Training triggers + live progress/loss in UI | SATISFIED (code) / HUMAN for live UX | /train + jobs.py; training.html + app.js polling + drawLossCurve |
| SC#6 | Configurable response storage, listed/auditionable in-app | SATISFIED | /settings + /responses; test_settings_roundtrip |
| SC#7 | Call→response flow end-to-end in-app | SATISFIED (code) / HUMAN for generation | /generate + generate.html + app.js; D-17 audition wired |
| SC#8 | Model version-history + rollback: runs.jsonl, /models, activate, pin persists | SATISFIED | registry.py + models.html + /models/activate + _active_checkpoint; test_app_models |

---

## Context Decisions Verified (05-CONTEXT.md)

| Decision | Status | Evidence |
|----------|--------|---------|
| D-11/D-15: canonical call.wav is server-rendered; browser synth is audition-only | HONORED | /ingest calls render() in-process; synth.js comment "NOT the canonical renderer" |
| D-13: reuse shipped load_manifest + load_notes validators | HONORED | app.py imports both; /ingest and /generate both call load_manifest |
| D-16: browser synth for interactive preview only | HONORED | synth.js never writes files; D-15 explicitly documented in code |
| D-17: response auditioned through call's own patch | HONORED | app.js:389-402; comment "// Audition response through the call's OWN patch (D-17)" |
| D-20: 3-op v1.1 spec (overrides UI-SPEC 4-op assumption) | HONORED | synth.js, editor.js, spec_constants.js all target N_OPERATORS=3 |
| D-02: app subprocesses train.py/generate.py (no in-process import) | HONORED | jobs.py subprocess.Popen; app.py subprocess.run for generate |
| APP-14 written by app layer, NOT train.py | HONORED | registry.py only called from jobs.py on_complete and app.py routes; train.py unchanged (git diff clean) |

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `apollo/app/app.py` | 32,36 | `shell=True` appears in COMMENTS only | Info | Not actual code; comments reference the threat model |
| `REQUIREMENTS.md` traceability | multiple | APP-04/05/06/09/10/11/13 still marked `[ ]` (unchecked) | Info | Documentation stale; all 7 are implemented and tested in the codebase |

No blockers. The REQUIREMENTS.md stale checkbox issue is a documentation artifact — the code, routes, tests, and templates for all 15 requirements are present and verified.

---

## Human Verification Required

### 1. Browser Navigation and Visual Rendering

**Test:** Run `python -m apollo.app` (or `.venv/bin/python -m apollo.app`), wait for the browser to open, and navigate through all 4 pages: `/`, `/corpus`, `/training`, `/generate`, `/models`.
**Expected:** All pages render correctly; 3-tile dashboard shows pair count at Display size; trust badge ("Runs on your machine — nothing is uploaded") visible on every page; navigation links work.
**Why human:** HTML layout, CSS token rendering (--accent #6D28D9 purple), and visual affordances require a real browser.

### 2. File-picker Ingest Flow (Drag-drop / Upload)

**Test:** On `/corpus`, click "Add pair", select a valid `.mid` and a `call_fm.json` (e.g. any preset from `apollo/app/presets/`), then click "Add pair".
**Expected:** Upload succeeds; page refreshes with the new pair listed; pair has a "Play call" button. Then try with an invalid JSON file — expect IngestError reason shown inline, no new pair appears.
**Why human:** Browser file-picker interaction and inline error surfacing require a real browser session with FormData upload.

### 3. Browser FM Synth Audition

**Test:** On `/corpus` with at least one pair, click the "Play call" button.
**Expected:** Audio plays through speakers; FM timbre is audible (not silence, not a crash).
**Why human:** Web Audio playback (`AudioContext`, `OscillatorNode`) requires a real browser with audio output; cannot be asserted programmatically.

### 4. Patch Editor Live Preview

**Test:** On `/generate`, load the "bright_bell" preset from the dropdown. Move the ratio slider for Operator 1. Click "Preview note".
**Expected:** A test note plays through the browser synth with the current patch; timbre changes as you edit. Enable the LFO section (warm_pad or vibrato_lead preset) — confirm tremolo or vibrato audible.
**Why human:** Real-time audio response to control changes and LFO audition require browser interaction.

### 5. Live Training Progress UI

**Test:** On `/training`, click "Train model" (with at least a few pairs present — even mock pairs work).
**Expected:** Status dot changes to training (purple); progress bar advances with each epoch; loss chart draws two lines (train solid purple, held dashed green); "Training complete — ready to generate" appears on finish.
**Why human:** Animated progress bar, canvas loss-curve rendering, and status polling (1s interval) require a live server and browser.

### 6. Model Version-History and Rollback

**Test:** After at least 2 training runs completed via the app (so `models/runs.jsonl` has 2+ rows), navigate to `/models`. Pin an older checkpoint via "Use this one". Trigger another training run. Confirm the pin persists after the new run completes. Then click "Use latest" and confirm the active badge moves to the newest.
**Expected:** Each training run appears with timestamp/pairs/losses; active badge shows current selection; pin survives a retrain; "Use latest" clears the pin.
**Why human:** Requires live training runs to populate the registry; stateful multi-step UX spanning training + /models interaction.

---

## Gaps Summary

No code gaps identified. All 15 requirements (APP-01 through APP-15) have corresponding server-side routes, client-side JS, templates, presets, and tests. The 42 Phase 5 app tests all pass (1 unrelated pre-existing Phase 7 test is the only failure in the full suite).

The `status: human_needed` reflects 6 items requiring browser interaction to confirm audio playback, visual rendering, and live UX — these are inherently untestable without a running browser+server. The automated verification is complete and clean.

**Security posture:** All 20 threat-model items (T-05-01 through T-05-20) have their mitigations in place and tested:
- Path traversal guards on /audio, /midi, /presets, /models/activate (T-05-01, T-05-04, T-05-12, T-05-15, T-05-17)
- Fixed-argv subprocess for train.py and generate.py — no shell=True, no user string in argv (T-05-09, T-05-14)
- In-process manifest validation before any filesystem write (T-05-08, T-05-13)
- Local-only binding 127.0.0.1 (T-05-02)

---

_Verified: 2026-06-03_
_Verifier: Claude (gsd-verifier)_

---
phase: 05-local-app-browser-synth
plan: "04"
subsystem: app-generate
tags: [flask, web-audio, fm-synth, patch-editor, generate, presets]
dependency_graph:
  requires: [05-01, 05-02, 05-03]
  provides: [patch-editor, generate-route, presets-route, responses-route]
  affects: [apollo/app/app.py, apollo/app/static/editor.js, apollo/app/static/app.js]
tech_stack:
  added: [editor.js (vanilla FM patch editor)]
  patterns: [checkBounds dual validation, fixed argv subprocess, traversal-safe allow-list]
key_files:
  created:
    - apollo/app/static/editor.js
    - apollo/app/templates/generate.html
    - apollo/app/presets/bright_bell.json
    - apollo/app/presets/warm_pad.json
    - apollo/app/presets/vibrato_lead.json
    - tests/test_app_generate.py
  modified:
    - apollo/app/app.py
    - apollo/app/static/app.js
decisions:
  - "Presets omit lfo key entirely when not applicable (bright_bell); server-validated via load_manifest"
  - "response_\\d+\\.mid allow-list uses anchored regex in _RESPONSE_FILENAME_RE module constant (T-05-15)"
  - "_latest_checkpoint uses max(mtime) over models/*.pt — consistent with RESEARCH OQ2"
  - "Subprocess argv uses fixed list ['python', '-m', 'apollo.scripts.generate', ckpt, call.mid] — no shell=True, no user strings"
  - "test_generate_no_checkpoint uses os.chdir to empty test_cwd to avoid any real models/*.pt on disk"
metrics:
  duration: "~6m"
  completed: "2026-06-04"
  tasks: 3
  files: 8
---

# Phase 5 Plan 04: Patch Editor + Generate Flow Summary

**One-liner:** In-browser 3-op FM patch editor wired to spec_constants.js BOUNDS + live Web Audio preview, plus call→response flow subprocessing generate.py with fixed argv and copying response to configurable store.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Patch editor (editor.js) + 3 bundled presets | 903fecc | editor.js, bright_bell.json, warm_pad.json, vibrato_lead.json |
| 2 | /generate + /presets + /responses routes + generate.html | 6f79f22 | app.py, generate.html |
| 3 | Editor wiring in app.js + generate/preset tests | b44d59f | app.js, test_app_generate.py |

## What Was Built

### editor.js (Task 1)
Vanilla JS patch editor (451 lines, > 80 minimum). Exposes `window.ApolloEditor`:
- `buildEditor(container)`: renders algorithm select (from ALGORITHMS), 3 `.op-panel` blocks with ratio/level/ADSR range+number inputs (min/max from `BOUNDS[field]`), master gain, and a `<details class="lfo-section">` collapsible LFO section with enable checkbox + rate/depth/wave/target controls
- `readPatch()`: collects values into call_fm.json object; lfo key OMITTED entirely when checkbox unchecked (absent = v1.0-identical server render)
- `validatePatch(patch)`: checks all fields via `checkBounds(value, field)` + LFO enum validation; returns {ok, errors[]}
- `previewNote()`: plays a 2-note test sequence (pitch 60+64, 0.4s each) through `ApolloSynth.playSequence`, debounced 150ms on any control change
- `loadPreset(obj)`: populates all inputs from a preset; sets LFO checkbox+fields
- `applyPresetByName(name)`: fetches from /presets/<name> then calls loadPreset

### Bundled presets (Task 1)
All 3 load via `apollo.synth.manifest.load_manifest` without raising:
- `bright_bell.json`: algorithm 0 (STACK), gain 0.85, no LFO
- `warm_pad.json`: algorithm 1 (PARALLEL_MODS), gain 0.7, slow tremolo LFO (rate 0.3Hz, depth 0.4)
- `vibrato_lead.json`: algorithm 2 (CARRIER_PAIR), gain 0.8, vibrato LFO (rate 5Hz, depth 0.6)

### Flask routes (Task 2, app.py)
- `GET /generate` → generate.html (patch editor mount point)
- `GET /presets` → sorted list of bundled preset stems
- `GET /presets/<name>`: allow-list `[a-z_]+` (T-05-12), abort(400) on mismatch, abort(404) if file missing
- `POST /generate`: load_manifest validation → allocate pair → check checkpoint (None → 400 + rmtree + UI-SPEC copy) → subprocess fixed argv → find newest response_*.mid → shutil.copy2 to RESPONSES_DIR → return {ok, nnn, response, checkpoint}
- `GET /responses` → {ok, responses: [names]}
- `/midi/<nnn>/<filename>` extended to accept `response_\d+\.mid` via anchored `_RESPONSE_FILENAME_RE` (T-05-15)

### generate.html (Task 2)
Extends base.html; 4 sections: MIDI upload, patch editor mount + preset dropdown + preview button, generate button + status, responses list with UI-SPEC empty-state copy ("No responses generated yet — upload or play a call, then hit Generate response to hear what Apollo plays back.")

### app.js wiring (Task 3)
Extended generate page block: buildEditor mount, preset dropdown population from /presets, preview button, generate button POSTing multipart FormData (call_mid + call_fm Blob), client-side validatePatch before POST, response audition through call's own patch (D-17), /responses refresh on load and after generate.

### Tests (Task 3 — tests/test_app_generate.py)
5 tests, all passing:
- `test_presets_listed_and_valid`: 3 names present, bright_bell returns valid JSON
- `test_preset_traversal_rejected`: `..`, URL-encoded traversal, uppercase, digits all → 400/404
- `test_generate_no_checkpoint`: cwd with empty models/ → 400 + "No trained model yet" + no orphan dir
- `test_generate_happy_path_stubbed`: monkeypatched subprocess.run writes response_001.mid → 200 + file copied to RESPONSES_DIR
- `test_responses_endpoint`: empty before generate, ≥1 .mid after stubbed generate

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. The editor serializes real FM parameters; the generate route calls real subprocess (stubbed in tests only); presets are full valid call_fm.json files.

## Threat Flags

No new threat surface beyond what is documented in the plan's threat register (T-05-12 through T-05-16). All mitigations implemented:
- T-05-12: /presets/<name> allow-list enforced
- T-05-13: load_manifest validates call_fm before any write
- T-05-14: fixed argv list, no shell=True, no user strings in argv
- T-05-15: anchored `_RESPONSE_FILENAME_RE` for /midi response filenames
- T-05-16: accepted (last 500 chars of stderr surfaced)

## Self-Check: PASSED

Files verified present:
- apollo/app/static/editor.js: FOUND
- apollo/app/templates/generate.html: FOUND
- apollo/app/presets/bright_bell.json: FOUND
- apollo/app/presets/warm_pad.json: FOUND
- apollo/app/presets/vibrato_lead.json: FOUND
- tests/test_app_generate.py: FOUND

Commits verified: 903fecc, 6f79f22, b44d59f — all present in git log.

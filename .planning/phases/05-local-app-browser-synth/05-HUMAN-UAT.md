---
status: partial
phase: 05-local-app-browser-synth
source: [05-VERIFICATION.md]
started: 2026-06-04
updated: 2026-06-04
---

## How to run

```bash
.venv/bin/python -m apollo.app
```
Boots the local server on `127.0.0.1` and opens the dashboard in your browser. Nothing leaves the device.

## Current Test

[awaiting human testing — start at test 1]

## Tests

### 1. Dashboard renders + local-only trust badge
expected: Page loads at 127.0.0.1 with three equal tiles (Corpus / Training / Generate), corpus pair-count vs the 30 target, and a persistent "local-only / on-device" trust badge. Navigation between Corpus / Training / Generate works.
result: [pending]

### 2. Drag-drop / file-picker ingest + inline error
expected: On Corpus, the "Add a pair" controls accept a `call.mid` + `call_fm.json` (and optional `response.mid`); a valid pair lands as `data/pairs/NNN/` (with `call.wav` re-rendered server-side) and appears in the list. An INVALID `call_fm.json` shows the exact IngestError reason inline and creates no orphan folder.
result: [pending]

### 3. Browser FM synth audition (Web Audio playback)
expected: Clicking a pair's "play call" audibly plays `call.mid` through the in-browser 3-op FM synth (you hear sound). Timbre tracks the patch; LFO patches produce audible tremolo/vibrato.
result: [pending]

### 4. Patch editor live preview + LFO
expected: On Generate, the patch editor exposes algorithm + per-op ratio/level/ADSR + a collapsible LFO section. Changing any control immediately previews a test note (audible). Loading each of the 3 bundled presets changes the sound. Enabling the LFO adds audible motion.
result: [pending]

### 5. Training: live progress bar + loss curve
expected: "Train model" starts a run; a progress bar advances by epoch and the loss-over-epochs canvas animates (train + held curves) via ~1s polling. The auto-retrain-on-upload toggle triggers one debounced run on a bulk add. The authoring UI stays responsive during training.
result: [pending]

### 6. Call→response generate + model version-history / rollback
expected: Generate with a trained checkpoint returns a playable `response.mid`, auditioned through the call's own patch, written to the configurable responses dir. With no checkpoint, you get the friendly "train first" message (no crash). On `/models`, the run history lists past runs (timestamp, loss, corpus size) with the active model badged; "Use this one" pins an older checkpoint and generation uses it; the pin survives a subsequent retrain until you re-pin / return to latest.
result: [pending]

## Summary

total: 6
passed: 0
issues: 0
pending: 6
skipped: 0
blocked: 0

## Gaps

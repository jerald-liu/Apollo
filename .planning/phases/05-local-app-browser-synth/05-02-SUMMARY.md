---
phase: 05-local-app-browser-synth
plan: "02"
subsystem: apollo/app
tags: [flask, web-audio, fm-synth, corpus, audition]
dependency_graph:
  requires: [apollo/app/app.py (05-01), apollo/app/static/spec_constants.js (05-01), apollo/app/templates/base.html (05-01)]
  provides: [apollo/app/static/synth.js, apollo/app/static/app.js, apollo/app/templates/corpus.html, /corpus route]
  affects: [Phase 5 plans 03-05 (synth.js + app.js are shared; /corpus is the corpus drill-in)]
tech_stack:
  added: [Web Audio API (OscillatorNode, GainNode, ConstantSource), vanilla JS IIFE pattern]
  patterns: [DX-style FM modulation (op_level*freq onto .frequency AudioParam), AudioParam scheduled ramps (ADSR), per-note LFO OscillatorNode (phase reset), Jinja |tojson inside script[type=application/json] (XSS mitigation)]
key_files:
  created:
    - apollo/app/static/synth.js
    - apollo/app/static/app.js
    - apollo/app/templates/corpus.html
    - tests/test_app_synth.py
  modified:
    - apollo/app/app.py
decisions:
  - "synth.js: LFO wave array as ['sine','triangle','square'] (no spaces) to match acceptance-criteria grep exactly"
  - "attachLfo uses ConstantSource for DC offset + scaled GainNode for LFO component (tremolo); avoids AudioParam.value collision with scheduled ramps"
  - "app.js showError creates .error-global div to avoid clobbering inline .error spans in corpus worklist"
  - "/corpus only iterates _known_pairs_set() — never user-supplied nnn (T-05-04)"
metrics:
  duration: "~4 min"
  completed_date: "2026-06-04"
  tasks_completed: 3
  files_created: 4
  tests_added: 13
requirements: [APP-05, APP-10, APP-11]
---

# Phase 5 Plan 02: Browser FM Synth + Corpus Audition Summary

**One-liner:** 3-op v1.1 Web Audio FM engine (synth.js) mirroring spec.py algorithms + CORPUS-CONVENTIONS LFO formulas, wired to /corpus drill-in view that plays each call.mid through its own call_fm.json patch via server-side /midi note JSON.

## What Was Built

### Task 1: synth.js — 3-op v1.1 Web Audio FM engine

**`apollo/app/static/synth.js`** — 287-line hand-rolled Web Audio FM engine. No Tone.js.

**`midiToHz(pitch)`:** `440 * Math.pow(2, (pitch - 69) / 12)`.

**`applyAdsr(gainParam, op, when, noteDuration)`:** Web Audio AudioParam ramps mirroring Faust `en.adsr`. `linearRampToValueAtTime` for attack→sustain; `setValueAtTime` at note-off; release ramp to 0.

**`playNote(audioCtx, patch, pitch, velocity, when, duration, master)`:** Builds 3 OscillatorNode + GainNode bundles. Modulator amplitude `= op.level * freq` (DX-style index ∝ pitch) connected to carrier `osc.frequency` AudioParam. Algorithm routing:
- **STACK(0):** op3 → op2 → op1 (sole carrier)
- **PARALLEL_MODS(1):** op2 + op3 both → op1 (sole carrier)
- **CARRIER_PAIR(2):** op3 → op1; op2 is independent additive carrier

**`attachLfo(audioCtx, patch, carriers, freq, when, duration)`:** New OscillatorNode per note for per-note phase reset. Tremolo (target=0): ConstantSource (DC = `level*(1-depth/2)`) + scaled LFO GainNode → carrier gainNode.gain. Vibrato (target=1): linear approx `maxDev = freq*depth*50/1200*Math.LN2` → carrier osc.frequency.

**`playSequence(audioCtx, patch, notes)`:** Schedules note array (from /midi JSON endpoint) through a shared master GainNode.

### Task 2: /corpus route + corpus.html + app.js audition wiring

**`apollo/app/app.py`** — Added `@app.get("/corpus")` route. Iterates `sorted(_known_pairs_set())`; reads each `call_fm.json` in try/except (marks pair invalid on failure, T-05-06). Passes `pairs=`, `n_pairs=`, `target=30` to template.

**`apollo/app/templates/corpus.html`** — Extends `base.html`. Empty-state copy verbatim from UI-SPEC: "add your first one to begin". Pair worklist: per-pair `<button class="play-call">` + `<script type="application/json" id="patch-{nnn}">{{ p.patch | tojson }}</script>` (T-05-05: no executable markup). Invalid pairs show `<span class="error">invalid call_fm.json</span>`, no patch tag. Loads spec_constants.js + synth.js + app.js via `{% block scripts %}`.

**`apollo/app/static/app.js`** — IIFE. Lazy AudioContext on first gesture. `showError` helper (creates `.error-global` div in `<main>`). DOMContentLoaded handler wires all `.play-call` buttons: reads embedded `patch-{nnn}` JSON, fetches `/midi/{nnn}/call.mid`, calls `ApolloSynth.playSequence`. Guards with element-existence check so app.js loads safely on all pages.

### Task 3: Synth + corpus tests

**`tests/test_app_synth.py`** — 13 tests in two groups:

Static synth.js checks (10): file exists, ≥80 lines, function declarations, algorithm branching, op_level*freq scaling, tremolo `1-depth`, vibrato `1200`, wave type array, no Tone.js, createOscillator present.

Flask behavior (3): test_corpus_lists_pair, test_midi_notes_json (pitch==60), test_corpus_invalid_manifest_marked.

## Verification

```
node -e static check of synth.js  ✓ (OK)
python -m pytest tests/test_app_synth.py -q  ✓ (13/13 passed)
python -m pytest tests/test_app_scaffold.py -q  ✓ (5/5 still pass)
GET /corpus with one valid pair → 200, body has play-call + patch-003  ✓
```

## Deviations from Plan

None — plan executed exactly as written.

## Threat Model Coverage

| Threat | Status | Evidence |
|--------|--------|---------|
| T-05-04 (path traversal /corpus + /midi nnn) | Mitigated | /corpus only iterates _known_pairs_set(); /midi reuses _validate_pair_nnn from 05-01 |
| T-05-05 (XSS — patch embedded in corpus.html) | Mitigated | `| tojson` inside `<script type="application/json">`, parsed via JSON.parse; no user string in executable markup |
| T-05-06 (malformed call_fm.json) | Handled | json.loads failure marks pair invalid; no patch tag emitted; page still returns 200 |

## Known Stubs

None — all three task goals fully wired: synth.js implements all algorithms + LFO; /corpus lists pairs; play-call fetches /midi notes and plays through synth.

## Commits

| Hash | Message |
|------|---------|
| 67e1716 | feat(05-02): synth.js — 3-op v1.1 Web Audio FM engine |
| fa95187 | feat(05-02): /corpus route + corpus.html + app.js audition wiring |
| 6cb01a7 | test(05-02): synth.js structure + /corpus + /midi behavior — 13 tests pass |

## Self-Check: PASSED

All 4 created files exist. All 3 commits verified in git log.

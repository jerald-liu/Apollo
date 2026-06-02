# Phase 5: Local App & In-Browser Synth - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-01
**Phase:** 05-local-app-browser-synth
**Areas discussed:** Backend architecture, Training UX & triggers, Input & response storage
**Not selected:** Synth fidelity & audio parity (audio-parity risk folded into Input discussion)

---

## Backend Architecture

| Question | Options | Selected |
|----------|---------|----------|
| Runtime | Local Flask server / Fully static offline / Python+WebSocket | Local Flask server ✓ |
| Invocation | Subprocess CLIs / Import as functions | Subprocess CLIs ✓ |
| Concurrency | Background job / Block until done | Background job ✓ |
| Launch | One command opens browser / Manual start | One command ✓ |

**Notes:** Mirrors the existing `apollo/eval/web/` Flask pattern; reuses shipped CLIs as-is.

---

## Training UX & Triggers

| Question | Options | Selected |
|----------|---------|----------|
| Retrain strategy | Full retrain from scratch / Warm-start from checkpoint | Full retrain from scratch ✓ |
| Auto-retrain debounce | Debounce then retrain / Immediate each upload / Queue when idle | Debounce ✓ |
| Progress streaming | Poll status endpoint / SSE | Poll ✓ |
| Training view | Progress bar + live loss curve / Bar + status only | Bar + live loss curve ✓ |

**Notes:** From-scratch aligns with the project train-from-scratch constraint; loss curve serves the educational emphasis.

---

## Input & Response Storage

| Question | Options | Selected |
|----------|---------|----------|
| Call input | Both upload + keyboard / Upload MIDI only / Keyboard only | Upload MIDI only ✓ |
| Audio parity (call.wav source) | Backend training-time renderer / In-browser render / Browser renders + retrain on it | Backend training-time renderer ✓ |
| Response storage | Configurable + default / Fixed dir / OS picker per save | Configurable + default ✓ |
| Pair validation | Reuse ingest validators server-side / Client-side check | Reuse ingest validators ✓ |

**Notes:** Upload-only narrows the UI-SPEC (keyboard authoring deferred). Audio-parity choice surfaced the central risk: no programmatic renderer exists (training audio = manual Ableton bounces), so a single canonical local renderer must serve both authoring and inference — flagged as #1 planning/research item.

## Claude's Discretion

- In-browser synth fidelity specifics (algorithm count, feedback, fixed/ratio modes).
- Debounce window, poll interval, loss-curve rendering approach.

## Deferred Ideas

- Play-a-call on the synth keyboard (in-app keyboard authoring).
- Synth-level / preset response output (already in backlog 999.1/999.2).

---

# Update Session — 2026-06-02 (Phase 6 renderer + Phase 7 LFO reconciliation)

**Areas discussed:** Canonical render path · Browser synth role/fidelity · FM-patch authoring UI · LFO authoring & audition
**Reason:** Phase 6 shipped `apollo/synth/render_call_wav` (the renderer the 2026-06-01 context flagged as the #1 missing risk); Phase 7 added the v1.1 optional LFO. The original synth/parity decisions needed reconciliation against shipped reality.

## Canonical Render Path

| Question | Options | Selected |
|----------|---------|----------|
| Canonical renderer for call.wav (authoring + inference) | Server-side Python (render_call_wav) / Browser-side Web Audio / Hybrid | Server-side Python ✓ |
| call.wav treatment | Always re-render from manifest / Accept provided call.wav / Defer to planning | Always re-render from manifest ✓ |

**Notes:** Resolves old D-11 risk — the canonical renderer now exists and is shipped. Manifest (`call_fm.json`) is the source of truth; uniform mel distribution guaranteed (no legacy-Ableton-bounce mix). → D-11(revised), D-14, D-15.

## Browser Synth Role / Fidelity

| Question | Options | Selected |
|----------|---------|----------|
| In-browser synth role | Interactive preview + live audition / Drop the Web Audio synth / Faithful audition mirror only | Interactive preview + live audition ✓ |
| Response.mid playback timbre | Same patch as the call / Fixed default / User-selectable | Same patch as the call ✓ (user-selectable deferred — "extend to 3 later") |

**Notes:** Browser synth mirrors 3-op v1.1 incl. LFO but never produces canonical audio. → D-16, D-17.

## FM-Patch Authoring UI

| Question | Options | Selected |
|----------|---------|----------|
| How user supplies call_fm.json | In-app patch editor + presets / Preset picker only / Upload raw JSON | In-app patch editor + presets ✓ |

**Notes:** Phase 6 explicitly handed "the synth UI" to Phase 5. Editor drives the live preview synth, writes call_fm.json. → D-18.

## LFO Authoring & Audition

| Question | Options | Selected |
|----------|---------|----------|
| v1.1 LFO handling | Editable + audible in v1 / Pass-through only / Audible but not editable | Editable + audible in v1 ✓ |

**Notes:** Collapsible LFO section in editor; preview renders tremolo/vibrato live to match server render. → D-19.

## Locked without discussion (housekeeping)

- 4-op → 3-op v1.1: UI-SPEC's 4-operator references overridden by the shared `apollo/synth/spec.py`. → D-20.

## New Deferred Ideas (this session)

- User-selectable / tweakable response audition timbre (v1 uses the call's own patch).

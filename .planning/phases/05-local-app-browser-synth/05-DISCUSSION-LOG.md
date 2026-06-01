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

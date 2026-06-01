# Phase 5: Local App & In-Browser Synth - Context

**Gathered:** 2026-06-01
**Status:** Ready for planning

<domain>
## Phase Boundary

A purely **local**, public-demonstration front-end that closes the whole Apollo loop in one app: drag-drop corpus building, an in-browser FM synth for audition, training triggers (manual + auto), a configurable response store, and a call→response flow. Its purpose is to show anyone — Ableton or not — that Apollo trains and generates **locally, on their machine, with their data never leaving the device**.

Depends only on shipped code (Phase 2 model + Phase 3 `train.py`/`generate.py`), so it is built as a parallel workstream alongside corpus tuning. Visual/interaction contract is locked in `05-UI-SPEC.md` (playful/educational, vanilla JS + Web Audio, dashboard + drill-in, equal emphasis on the three flows) — not re-litigated here.

</domain>

<decisions>
## Implementation Decisions

### Backend Architecture
- **D-01:** Runtime is a **local Flask server** bound to `127.0.0.1`, reusing the existing `apollo/eval/web/` pattern. Serves the dashboard page + JSON endpoints that drive the model. "Local-only" is preserved; nothing is uploaded off-device.
- **D-02:** The app **subprocesses the existing CLIs** (`python -m apollo.scripts.train` / `apollo.scripts.generate`) rather than importing them in-process. Reuses shipped, tested code as-is; clean isolation; status derived from stdout + emitted artifacts.
- **D-03:** Training runs as a **background job** (worker/subprocess); the dashboard stays responsive and streams progress. Supports the "keep adding pairs while it trains" flow.
- **D-04:** Launch is **one command** (e.g. `python -m apollo.app`) that boots the server and opens the browser to the dashboard.

### Training UX & Triggers
- **D-05:** Each run is a **full retrain from scratch** on the whole corpus (no warm-start). Aligns with the project's train-from-scratch constraint (see CLAUDE.md), is reproducible, and the tiny corpus keeps it fast — and it makes "watch it learn locally" a real demo moment.
- **D-06:** Manual **"Train model"** button always available; an **auto-retrain-on-upload** setting toggles automatic runs. Auto-retrain is **debounced** (wait a few seconds after the last upload) so a bulk drag-in of N pairs triggers one run, not N.
- **D-07:** Live progress reaches the browser via **polling a status endpoint** (~1s) for epoch/loss — simplest robust path with vanilla JS + Flask, no extra deps.
- **D-08:** The training view shows **both a progress bar and a live loss-over-epochs curve** — serves the educational emphasis (viewers see the model improving).

### Input & Response Storage
- **D-09:** Call input is **MIDI upload only** for v1 of this phase. (Refines the UI-SPEC, which had floated play-on-keyboard — that is deferred; see Deferred Ideas.)
- **D-10:** The in-browser synth's role is **audition/playback only** (hear call and response). It is NOT the keyboard authoring tool and NOT (by itself) the canonical audio renderer for model input — see D-11.
- **D-11:** **Audio parity principle (locked):** the `call.wav` fed to the mel encoder at inference MUST be produced by the **same renderer that produced the corpus `call.wav`**, to avoid a train/inference mel-distribution mismatch that would degrade generation. Implementation of that renderer is the #1 research/planning item (see Specifics — this is the central technical risk).
- **D-12:** Generated responses are written to a **configurable location with a sensible default** (e.g. `data/responses/`), changeable via an in-app setting; responses are listed and auditionable in-app.
- **D-13:** Dragged-in pairs are **validated server-side by reusing the existing ingest validators** (`apollo/ingest`, against `data/pairs/CORPUS-CONVENTIONS.md`), surfacing the same errors — one source of truth, no client/server drift.

### Claude's Discretion
- In-browser synth fidelity specifics (how many of Operator's algorithms, feedback paths, fixed/ratio modes) were not discussed — left to research/planning, constrained by the UI-SPEC and the audio-parity principle (D-11). Note: because the synth is audition-only (D-10), strict training-fidelity is NOT required of it *unless* the chosen renderer (D-11) ends up being the browser synth itself.
- Exact debounce window (D-06), poll interval (D-07), and loss-curve rendering approach (D-08) are implementation details.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Design & scope
- `.planning/phases/05-local-app-browser-synth/05-UI-SPEC.md` — locked visual/interaction contract (aesthetic, stack, layout, tokens, copywriting). Authoritative for all UI.
- `.planning/ROADMAP.md` §"Phase 5: Local App & In-Browser Synth" — goal, success criteria, parallelizability, in-browser-Operator research note.
- `CLAUDE.md` — project constraints; note the **train-from-scratch** rule (D-05) and local-only ethos.

### Reusable code (this phase wraps, does not rewrite)
- `apollo/eval/web/` (`app.py`, `templates/`, `static/style.css`, `static/grade.js`) — the Flask + vanilla pattern to mirror (D-01).
- `apollo/scripts/train.py`, `apollo/scripts/generate.py` — the CLIs the app subprocesses (D-02).
- `apollo/ingest/` + `data/pairs/CORPUS-CONVENTIONS.md` — pair validation rules to reuse server-side (D-13).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Flask + vanilla web surface** (`apollo/eval/web/`): proven local-only server pattern (127.0.0.1), CSS token system the UI-SPEC extends. Mirror its structure for the new app.
- **CLIs** (`train.py`, `generate.py`): full training + autoregressive inference already shipped and tested — drive via subprocess (D-02).
- **Ingest validators** (`apollo/ingest/`): pair discovery + format/`call.wav` checks; reuse for drag-drop validation (D-13).

### Established Patterns
- Local-only, 127.0.0.1 binding; no external calls. Carry into the new app.
- `eval/runs.jsonl` / `scores.jsonl` style append-only logs — a precedent for recording training runs / generated responses if useful.

### Integration Points
- New app likely lives under `apollo/app/` (or `apollo/web/`) with its own `__main__` for the one-command launch (D-04).
- Writes pairs into `data/pairs/NNN/`; writes responses into the configurable store (D-12); invokes `models/`-producing training (D-05).

</code_context>

<specifics>
## Specific Ideas

**#1 risk — the canonical local audio renderer (D-11).** There is currently **no programmatic renderer** in the repo: training `call.wav` files are *manual Ableton Operator bounces*. Since this app must work with no Ableton, parity has to be achieved a different way. Research must choose and the planner must spec one of:
  - **(a)** A headless/offline-audio render of the in-browser FM synth used as the single canonical renderer for BOTH app-authored corpus `call.wav` AND inference `call.wav` (parity by construction; commits the synth to training-grade fidelity).
  - **(b)** A separate deterministic server-side FM renderer shared by authoring + inference.
  - **Key implication:** models trained via this app should be trained on app-rendered audio, not the legacy hand-bounced corpus, so the mel distribution matches at inference. Mixing legacy Ableton-bounced pairs with app-rendered pairs risks distribution mismatch.

</specifics>

<deferred>
## Deferred Ideas

- **Play-a-call on the synth keyboard** (in-app MIDI authoring via the keyboard) — UI-SPEC floated it; deferred in favor of MIDI upload only for this phase (D-09). Natural follow-up once the synth + renderer are solid.
- **Synth-level / preset response output** — already tracked in backlog Phase 999.1/999.2; not part of this app.
- None of the discussion introduced new model capabilities — scope stayed within the demo-app boundary.

</deferred>

---

*Phase: 05-local-app-browser-synth*
*Context gathered: 2026-06-01*

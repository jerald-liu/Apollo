# Phase 5: Local App & In-Browser Synth - Context

**Gathered:** 2026-06-01
**Updated:** 2026-06-02 (reconciled against shipped Phase 6 renderer + Phase 7 v1.1 LFO)
**Status:** Ready for planning

<domain>
## Phase Boundary

A purely **local**, public-demonstration front-end that closes the whole Apollo loop in one app: drag-drop corpus building, an **in-app FM patch editor + in-browser synth for audition**, training triggers (manual + auto), a configurable response store, and a call→response flow. Its purpose is to show anyone — Ableton or not — that Apollo trains and generates **locally, on their machine, with their data never leaving the device**.

Depends only on shipped code (Phase 2 model + Phase 3 `train.py`/`generate.py` + **Phase 6 `apollo/synth/` renderer** + **Phase 7 v1.1 LFO**), so it is built as a parallel workstream alongside corpus tuning. Visual/interaction contract is in `05-UI-SPEC.md` (playful/educational, vanilla JS + Web Audio, dashboard + drill-in) — **except** that the UI-SPEC's 4-operator assumption is overridden: the synth targets the shared **3-op v1.1 FM spec** (see D-19).

</domain>

<decisions>
## Implementation Decisions

### Backend Architecture (carried forward from 2026-06-01 — still valid)
- **D-01:** Runtime is a **local Flask server** bound to `127.0.0.1`, reusing the existing `apollo/eval/web/` pattern. Serves the dashboard page + JSON endpoints. "Local-only" preserved; nothing uploaded off-device.
- **D-02:** The app **subprocesses the existing CLIs** (`python -m apollo.scripts.train` / `apollo.scripts.generate`) rather than importing them in-process. Reuses shipped, tested code; status derived from stdout + emitted artifacts.
- **D-03:** Training runs as a **background job**; the dashboard stays responsive and streams progress. Supports "keep adding pairs while it trains."
- **D-04:** Launch is **one command** (e.g. `python -m apollo.app`) that boots the server and opens the browser to the dashboard.

### Training UX & Triggers (carried forward — still valid)
- **D-05:** Each run is a **full retrain from scratch** on the whole corpus (no warm-start). Aligns with the train-from-scratch constraint; tiny corpus keeps it fast; makes "watch it learn locally" a real demo moment.
- **D-06:** Manual **"Train model"** button always available; an **auto-retrain-on-upload** setting toggles automatic runs, **debounced** so a bulk drag-in of N pairs triggers one run, not N.
- **D-07:** Live progress reaches the browser via **polling a status endpoint** (~1s) for epoch/loss.
- **D-08:** The training view shows **both a progress bar and a live loss-over-epochs curve** (educational emphasis).

### Render Path & Audio Parity (UPDATED — old "#1 risk" resolved by Phase 6)
- **D-11 (revised — LOCKED):** **Audio parity by construction.** The `call.wav` that feeds the mel encoder — for **both** corpus authoring **and** inference — is produced **server-side by the shipped Phase 6 renderer `apollo.synth.render_call_wav(manifest_path, mid_path)`** (DawDreamer + Faust, deterministic, normalized, 3-op v1.1). This is the *same* engine + manifest that produced the corpus, so there is no train/serve mel-distribution gap. *(Supersedes the 2026-06-01 D-11, which framed "choose a canonical renderer" as the central open risk — that renderer now exists and is shipped.)*
- **D-14 (new — LOCKED):** **`call_fm.json` is the source of truth; `call.wav` is always (re)rendered from it.** Every pair must carry a `call_fm.json` FM-patch manifest. The app renders `call.wav` from the manifest via `render_call_wav` and treats that as the only valid audio; a dropped-in/legacy `call.wav` is ignored/regenerated. Guarantees one uniform mel distribution across the corpus (no legacy-Ableton-bounce vs. synth-render mix).
- **D-15 (new — LOCKED):** The in-browser Web Audio synth **never produces training or inference audio.** It is interactive/audition only (see D-16). Canonical persisted audio is always server-rendered.

### In-Browser Synth Role (UPDATED — redefined around server-side canonical render)
- **D-16 (revised — LOCKED):** The browser synth is for **interactive preview + live audition**: hear a patch live while editing it (drives the patch editor, D-18), and play the generated `response.mid` live. It **mirrors the 3-op v1.1 spec including the LFO** so what the user hears tracks the server render — but it is explicitly NOT the canonical renderer (D-15). *(Replaces 2026-06-01 D-10's narrower "audition/playback only" framing with the editor-preview role.)*
- **D-17 (new — LOCKED):** The generated **`response.mid` is auditioned through the call's own `call_fm.json` patch** in v1 — reinforces the "you answering yourself" core value (same instrument, same timbre). *(User-selectable / tweakable response timbre is a deferred follow-up — see Deferred Ideas.)*

### FM-Patch Authoring (NEW — Phase 6 handed "the synth UI" to this phase)
- **D-18 (new — LOCKED):** Authoring uses an **in-app 3-op FM patch editor + bundled presets.** The editor exposes per-operator ratio/level/ADSR, the algorithm choice, and the optional LFO (D-19); bundled presets are starting points; **live preview** is rendered by the browser synth (D-16); on save it writes a valid `call_fm.json`. This is the showpiece authoring flow and the largest UI surface of the phase.
- **D-19 (new — LOCKED):** **LFO is editable + audible in v1.** The patch editor exposes an **optional/collapsible LFO section** (rate / depth / wave / target per the v1.1 schema); the preview synth renders tremolo/vibrato live to match the server render. Honors Phase 7's spec end-to-end in the demo.

### Corpus Ingest & Response Storage (carried forward, adjusted for manifest-based pairs)
- **D-09 (revised):** Call input is **MIDI upload (`call.mid`) paired with an in-app authored `call_fm.json`** (D-18). *(Play-on-keyboard MIDI authoring remains deferred — see Deferred Ideas.)*
- **D-12:** Generated responses are written to a **configurable location with a sensible default** (e.g. `data/responses/`), changeable via an in-app setting; responses are listed and auditionable in-app (via D-16/D-17).
- **D-13:** Dragged-in pairs are **validated server-side by reusing the existing ingest + synth validators** (`apollo/ingest`, `apollo.synth.load_manifest`, against `data/pairs/CORPUS-CONVENTIONS.md`), surfacing the same errors — one source of truth, no client/server drift. The manifest validation includes the v1.1 `lfo` rules (lfo requires spec_version 1.1; bounds/enum checks).

### Spec Reconciliation (NEW — housekeeping, locked without discussion)
- **D-20 (new — LOCKED):** The synth/editor targets the **3-operator v1.1 FM spec** (`apollo/synth/spec.py`, `SPEC_VERSION = "1.1"`). The UI-SPEC's **4-operator** references (SC#4 language) are **overridden** — the shared spec is authoritative. Algorithm set, operator params, envelope semantics, and the LFO schema all come from `apollo/synth/spec.py`, not re-invented in JS.

### Claude's Discretion
- The exact preset set, patch-editor layout/control widgets, debounce window (D-06), poll interval (D-07), and loss-curve rendering (D-08) are implementation details for research/planning.
- How the browser synth's Web Audio graph approximates the DawDreamer/Faust 3-op + LFO sound closely enough for audition (it need not be bit-faithful — it is never canonical, D-15). Choosing the Web Audio operator-graph topology vs. a helper lib is a research item (see Specifics).
- Whether server-side render of `call.wav` is invoked in-process (`import apollo.synth`) or via subprocess — distinct from D-02's CLI subprocessing; planner decides.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Shared FM spec (authoritative for the synth + editor)
- `apollo/synth/spec.py` — **single source of truth**: `SPEC_VERSION="1.1"`, `Algorithm`, `OperatorParams`, `FmParams`, `LfoWave`/`LfoTarget`/`LfoParams`, `dsp_string`. The browser synth + patch editor (D-18/D-19/D-20) must mirror THIS.
- `apollo/synth/manifest.py` — `load_manifest` validation rules (spec_version {1.0,1.1}, lfo-requires-1.1, bounds/enum checks) to reuse server-side (D-13).
- `apollo/synth/render.py` — `render_call_wav(manifest_path, mid_path)` + `render(params, notes)`: the canonical render entry points (D-11/D-14).
- `data/pairs/CORPUS-CONVENTIONS.md` — manifest schema doc incl. the v1.1 `lfo` block + tremolo/vibrato parity formulas the browser synth must match (D-16/D-19).

### Design & scope
- `.planning/phases/05-local-app-browser-synth/05-UI-SPEC.md` — visual/interaction contract (aesthetic, stack, layout, tokens, copywriting). Authoritative for UI **except** the 4-op assumption, overridden by D-20.
- `.planning/ROADMAP.md` §"Phase 5: Local App & In-Browser Synth" — goal, success criteria, cross-phase + LFO notes. NB: SC#4/SC#7 say the in-browser synth renders `call.wav`; D-11/D-15 reinterpret that — canonical render is server-side, browser synth is audition/preview.
- `CLAUDE.md` — project constraints; train-from-scratch rule (D-05), local-only ethos.

### Reusable code (this phase wraps, does not rewrite)
- `apollo/eval/web/` (`app.py`, `templates/`, `static/style.css`, `static/grade.js`) — the Flask + vanilla pattern to mirror (D-01).
- `apollo/scripts/train.py`, `apollo/scripts/generate.py` — the CLIs the app subprocesses (D-02).
- `apollo/ingest/` — pair discovery + format/`call.wav` checks; reuse for drag-drop validation (D-13).

### Spike findings (MUST honor — see skill)
- `.claude/skills/spike-findings-apollo/` — DawDreamer/Faust gotchas (integer-index polyphony params, benign `undefined symbol : effect` warning filter, `dawdreamer.__version__` absent) and mel-conditioning patterns. Relevant whenever the app invokes `apollo/synth`.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Phase 6 synth renderer** (`apollo/synth/`): `render_call_wav`, `render`, `load_manifest`, `dsp_string`, full 3-op v1.1 + LFO spec. The app drives this server-side for all canonical audio (D-11/D-14) and validation (D-13).
- **Flask + vanilla web surface** (`apollo/eval/web/`): proven local-only server pattern (127.0.0.1), CSS token system the UI-SPEC extends. Mirror its structure.
- **CLIs** (`train.py`, `generate.py`): full training + autoregressive inference shipped + tested — drive via subprocess (D-02).
- **Ingest validators** (`apollo/ingest/`): pair discovery + format/`call.wav` checks; combine with `synth.load_manifest` for drag-drop validation (D-13).

### Established Patterns
- Local-only, 127.0.0.1 binding; no external calls.
- `eval/runs.jsonl` / `scores.jsonl` append-only logs — a precedent for recording training runs / generated responses if useful.
- Manifest-as-source-of-truth (Phase 6): a pair = `call.mid` + `call_fm.json` → rendered `call.wav` + `response.mid`. The app's ingest/authoring must produce exactly this shape.

### Integration Points
- New app likely lives under `apollo/app/` (or `apollo/web/`) with its own `__main__` for one-command launch (D-04).
- Writes pairs into `data/pairs/NNN/` (each with `call.mid` + `call_fm.json`, app re-renders `call.wav`); writes responses into the configurable store (D-12); invokes `models/`-producing training (D-05).
- Patch editor (D-18) ↔ browser preview synth (D-16) ↔ server `render_call_wav` (D-11) must all agree on the same `call_fm.json` schema from `apollo/synth/spec.py`.

</code_context>

<specifics>
## Specific Ideas

**New #1 technical item (the old "no renderer exists" risk is RESOLVED):** the browser synth + patch editor must **re-implement the 3-op v1.1 FM spec — including LFO tremolo/vibrato — in Web Audio**, closely enough for *audition* (it is never canonical, D-15), and the editor must serialize to a `call_fm.json` that the server's `load_manifest`/`render_call_wav` accept verbatim. Research/planning must:
  - Map `apollo/synth/spec.py` (operators, algorithms, ADSR, `LfoWave`/`LfoTarget`, the tremolo `1 - depth*(1-lfo_uni)` and vibrato `pow(2, lfo_bi*depth*50/1200)` formulas in `CORPUS-CONVENTIONS.md`) onto a Web Audio `OscillatorNode`/`GainNode` graph (Tone.js `FMSynth` is 2-op only — insufficient).
  - Keep the JS schema and the Python schema in lockstep (one is generated/derived from the other if feasible) so the editor never emits a manifest the server rejects.
  - Decide in-process vs. subprocess invocation of `render_call_wav` for the live "render this pair's canonical call.wav" action.

**Parity demo moment:** because canonical `call.wav` is server-rendered (D-11) and the response is auditioned through the call's own patch (D-17), the app can honestly show "this is exactly the audio the model is trained/served on" — a stronger local-first story than a browser-only re-render.

</specifics>

<deferred>
## Deferred Ideas

- **Play-a-call on the synth keyboard** (in-app MIDI authoring via the keyboard) — UI-SPEC floated it; still deferred in favor of MIDI upload + patch editor for this phase (D-09). Natural follow-up once the synth + editor are solid.
- **User-selectable / tweakable response audition timbre** — v1 plays `response.mid` through the call's own patch (D-17); letting the user choose or edit a separate response patch is a deferred enhancement ("extend to 3 later" per discussion).
- **Synth-level / preset response output** (model answering with synthesis params / CC tokens) — tracked in backlog Phase 999.1/999.2 and partially promoted to Phase 7 (SYNTH-01, call-side); not part of this app.
- **4-op / 11-algorithm / filter synth topology** — deferred at the spec level to `SEED-009` (Phase 6 decision); Phase 5 targets the shipped 3-op v1.1 spec (D-20).
- None of the discussion introduced new model capabilities — scope stayed within the demo-app boundary.

</deferred>

---

*Phase: 05-local-app-browser-synth*
*Context gathered: 2026-06-01 · Updated: 2026-06-02 (Phase 6 renderer + Phase 7 LFO reconciliation)*
</content>
</invoke>

# Phase 4: Evaluation Loop - Context

**Gathered:** 2026-05-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Tooling that closes the active-learning loop: a rubric for scoring held-out responses, a grader that lets the user actually sit down and assign scores, persistent per-run score storage, a delta surface that shows how scores moved iteration-over-iteration, and a ship-gate command that says whether v1 is ready.

The phase delivers REQs EVAL-01 through EVAL-05 and produces the artifact set users interact with for every iteration round: a web UI for grading, a Max-for-Live render device for getting `response.mid` into audio inside Ableton, a JSONL score store, and a notebook for visual delta inspection.

**Not in this phase:** the corpus itself (Phase 3), training (Phase 3), inference / `generate.py` (Phase 3). Phase 4 consumes their outputs.

</domain>

<decisions>
## Implementation Decisions

### Rubric (EVAL-01)
- **D-01:** Two scoring dimensions per response: **call-response fit (1–5)** and **musical coherence (1–5)**. Two is the deliberate ceiling — 30 held-out pairs × 2 dims keeps each grading session ~5–10 min, which is the cadence the active-learning loop needs to actually happen.
- **D-02:** Both scales have **written anchors per scale point** (e.g. 1 = "unrelated", 3 = "plausible response", 5 = "exactly what I'd play"). Anchors are documented once and shown in the grader UI. This is non-negotiable for the "improvement across iterations" signal to mean anything — without anchors, scoring drifts across weeks and the ship gate is meaningless.
- **D-03:** Each pair carries an **optional free-text note**. Captures the qualitative gap-finding signal that drives the next authoring round ("response keeps landing on the tonic, boring" is more actionable than a 2). Optional, not mandatory — friction kills iteration.

### Grading Workflow / UX (EVAL-02)
- **D-04:** Grader is a **tiny local web UI** (Flask/FastAPI + plain HTML). Lists held-out pairs as a worklist; clicking a row plays `call.wav` then `response.wav` back-to-back, then exposes sliders/keys for the two scores + the note field. Submits write incrementally to the score store. Sessions are **resumable** — partial progress survives a close/reopen.
- **D-05:** Grading is **blind by default with a reveal toggle**. The UI hides which run/checkpoint produced each response while you're scoring (critical because the user is both training target and grader — bias risk is real). A toggle lets you peek post-hoc for diagnostics.
- **D-06:** Session model is **all held-out pairs, one sitting, resumable** — designed for the focused 5–10 min sitting, not enforced batching.
- **D-07:** Response audio is **pre-rendered once per run**, not rendered live during grading. After a training run, the user batch-renders all held-out responses to `.wav` via the Max-for-Live device (see D-09); the grader plays those `.wav`s with no Ableton interaction during scoring.

### Score Persistence + Delta Surface (EVAL-03, EVAL-04)
- **D-08:** Score store is **JSONL, one record per (run, pair, dimension)** at `eval/scores.jsonl`. Append-only, git-diffable, no schema migrations. A separate `eval/runs.jsonl` carries one record per run with run-level metadata. *Run-level metadata fields are Claude's discretion at plan time — see "Claude's Discretion" below.*
- **D-09:** **Run identity is auto-derived** — short hash of (checkpoint file bytes + sorted training pair-IDs) plus a human-readable timestamp. No manual tagging required for identity. Reproducible: same checkpoint on same corpus = same ID.
- **D-10:** Delta surface is a **Jupyter notebook with matplotlib plots** at `eval/delta.ipynb`. Reads `scores.jsonl` + `runs.jsonl` and shows per-dimension mean across runs over time, plus per-pair score trajectories. Notebook beats a static report for the user's exploratory style and scales naturally as iteration count grows.

### Audio Rendering — Max-for-Live Device
- **D-11:** A **Max-for-Live device** handles response rendering. The device sits on the response track (one instance per held-out pair, or one configurable instance that walks the held-out set — planner decides). Given a `response.mid` file path, it loads the MIDI into the clip slot, plays it through the loaded Operator preset, and bounces the result to `data/pairs/NNN/eval/{run_id}/response.wav`.
- **D-12:** The device is **rendering-only in Phase 4** — it does not handle grading (that's the web UI) and does not handle corpus authoring (Phase 3 ships a stopgap Python folder-watcher / manual bounce convention for `call.wav` exports).
- **D-13:** Two device instances (call track + response track) are **independent** and **coordinate via folder convention** — `data/pairs/NNN/` is the shared protocol. No M4L inter-device messaging, no Live API globals.

### Ship-Gate Mechanics (EVAL-05)
- **D-14:** **Improvement = mean call-response-fit up by any ε** between the two designated runs. Strict literal reading of EVAL-05. Musical coherence is *tracked but not gating* — it informs diagnostics, not the ship decision.
- **D-15:** **No per-pair regression tolerance** — mean is what counts. Per-pair regressions are surfaced in the delta notebook for diagnostic value (which authored gestures the model is losing) but do not block the gate.
- **D-16:** **The two consecutive runs are identified via an explicit iteration marker.** Not every run counts as an "iteration boundary" — exploratory runs (sweeps, debug, ablations) can exist without being gate-eligible. The user flags a run as `iteration: true` (or similar) when they want it to count. The ship gate looks at the two most recent iteration-marked runs and checks consecutive improvement against the one before them.
- **D-17:** Ship-gate is announced via **`apollo eval ship-check`** — a CLI subcommand that returns exit code 0 if the gate is met (last two iteration-marked runs both improved over their respective predecessors), non-zero otherwise. Prints a banner with the two deltas. No auto-tagging, no auto-ship action — the user decides what to do once the gate trips.

### Claude's Discretion
- Exact run-level metadata fields in `runs.jsonl` (D-08) — at minimum: checkpoint hash, corpus pair-ID list, training config snapshot, timestamp, iteration marker (D-16). Planner may add fields as needed (e.g. git SHA, total training steps).
- File layout details under `eval/` (subdirs, naming conventions).
- Web UI tech stack within the "local web UI" constraint (Flask vs FastAPI vs http.server + static HTML — whichever is cheapest to build).
- M4L device internal architecture and how the held-out walk-through is parameterized.
- Notebook structure / which specific plots beyond the obvious "mean per dim over time" and "per-pair trajectory".

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project-level
- `.planning/PROJECT.md` — overall project context, ship criterion, constraints. Active-learning loop is the product.
- `.planning/REQUIREMENTS.md` — EVAL-01 through EVAL-05 are the requirements this phase delivers; cross-check coverage.
- `.planning/ROADMAP.md` §"Phase 4: Evaluation Loop" — goal, dependencies, success criteria.

### Prior-phase context this phase builds on
- `.planning/phases/01-tokenizer-ingest/01-CONTEXT.md` — deterministic hash-based held-out split; eval consumes this set.
- `.planning/phases/02-model-training/` — checkpoint artifact format (single file under `models/`); run identity (D-09) hashes the checkpoint bytes.
- `.planning/phases/03-corpus-inference/` (when written) — `generate.py` is the upstream producer of `response.mid` files the eval loop scores.

### External — none
No external specs or ADRs apply. All requirements are captured in REQUIREMENTS.md + decisions above.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `apollo/ingest/split.py` — deterministic held-out split. Eval pipeline calls this to enumerate the held-out pair list for a given corpus.
- `apollo/ingest/pairs.py` — pair discovery + path resolution. Eval uses the same pair-folder layout.
- Tokenizer + MelExtractor are not directly used in eval, but the checkpoint they were trained against is what eval grades.

### Established Patterns
- CLI subcommands live under `apollo/scripts/` (per Phase 1 pattern). `apollo eval` will be a new subcommand group.
- Tests under `tests/test_*.py`, one file per module/CLI. Eval will add `test_scoring.py`, `test_run_identity.py`, `test_ship_check.py` at minimum.
- Artifact persistence already uses JSON for tokenizer config (Phase 1 precedent for JSON/JSONL choice).

### Integration Points
- Eval reads checkpoint artifacts from `models/` (Phase 2 output format).
- Eval invokes `generate.py` (Phase 3) once per held-out pair to produce `response.mid` files for a given checkpoint.
- M4L device reads/writes inside `data/pairs/NNN/eval/{run_id}/` — extends the existing pair folder convention rather than introducing a new top-level dir.

</code_context>

<specifics>
## Specific Ideas

- The web UI should feel like opening a single page, hitting play 30 times, sliding two sliders each time, and being done in ~10 minutes. Anything more elaborate is over-built for v1.
- Blind grading: the UI shouldn't display run IDs, checkpoint paths, or timestamps in the scoring view. A reveal button shows them after a score is submitted (or on demand for debugging).
- The Max-for-Live device is a Phase-4 build, not a Phase-3 build. Phase 3 corpus authoring uses a stopgap workflow (Python folder watcher + manual Ableton bounce) and the device replaces nothing in Phase 3.
- Notebook delta view is preferred over a static markdown report because the user expects to explore — e.g. "what changed for pair 17 specifically", "show me per-pair trajectories sorted by latest delta". Static reports calcify too quickly.

</specifics>

<deferred>
## Deferred Ideas

- **Corpus Training device (authoring mode).** During discussion the idea surfaced of one Max-for-Live device family handling both corpus authoring (exporting `call.mid`/`call.wav`/`response.mid` from Ableton) AND eval rendering. Decision was to scope Phase 4's M4L work to rendering only; the authoring side lives in Phase 3 as a stopgap (Python folder watcher / manual bounce). If the stopgap proves friction-heavy, promote "Corpus Training authoring-mode M4L device" to its own future phase or fold into a Phase-3 extension.
- **In-session grading (M4L-native scoring UI).** Initial direction was to let grading happen inside Ableton via the device's own UI. Rejected in favor of a separate web UI to keep Phase 4 build cost down and separate concerns (rendering vs grading). Revisit if the web-UI-plus-Ableton context-switch turns out to be the friction killing iteration cadence.
- **Plot/report tooling beyond the notebook.** A `apollo eval report` markdown writer was considered. Not in v1 — notebook covers exploratory needs, ship-check command covers the gate. Add a static report only if external sharing becomes a need.
- **Per-dim ship-gating, regression caps, threshold improvements (ε floors).** All considered, all rejected for v1 in favor of strict literal EVAL-05 (mean fit up by any ε). Revisit if the gate trips spuriously on noise.
- **Auto-tagging checkpoints when the gate passes.** Considered, rejected — user keeps manual control over what counts as "shipped".

</deferred>

---

*Phase: 04-evaluation-loop*
*Context gathered: 2026-05-21*

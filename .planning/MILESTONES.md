# Milestones

Shipped and in-progress milestone history for Apollo.

## v1.0 — MAESTRO piano transformer (DEPRECATED)

Trained a transformer on MAESTRO piano. Hit a representation-level dynamics blocker (MAESTRO's 91–95% pedal-active prior was load-bearing in the output distribution). Deferred; codebase lives on the `deprecated` branch as historical reference only — *not* a model lineage.

## v2.0 — Call-and-Response v1 (SHIPPED, code-complete)

On-device, style-preserving call→response MIDI generator. Seven phases:

- **Phase 1 — Tokenizer & Ingest:** MIDI tokenizer, mel extractor (96,128), pair discovery, hash split, artifact format.
- **Phase 2 — Model & Training:** MelEncoder + ApolloModel (causal transformer, mel prefix), masked response-only loss, smoke train (type_acc=1.0), checkpoints.
- **Phase 3 — Corpus & Inference:** CORPUS-CONVENTIONS, `generate.py`, `train.py` (real-corpus).
- **Phase 4 — Evaluation Loop:** listen-test rubric, blind grading UI, per-iteration score tracking, ship gate.
- **Phase 5 — Local App & In-Browser Synth:** local Flask app — drag-drop pair ingest, browser FM synth + patch editor, training view, call→response, model version-history + rollback.
- **Phase 6 — Synth-Independent Corpus Rendering:** owned 3-op FM spec + headless DawDreamer/Faust `render_call_wav` (dropped the Ableton/Operator manual-bounce dependency).
- **Phase 7 — Synth Automation (LFO):** optional per-patch v1.1 LFO (rate/depth/wave/target), backward-compatible.

**Status:** code-complete (Phases 1–7 shipped, merged to `main` via PR #23). Ship gate (EVAL-05: two consecutive improving held-out iterations) unmet — depends on an authored corpus.

## v3.0 — fm4synth canonical synth + local corpus-authoring app (IN PROGRESS)

Replace the owned Faust 3-op renderer with the `fm4synth` engine (Rust, 4-op matrix + multi-LFO) as the canonical synth, and build a local public-demo authoring app to create call/response bassline pairs — fueling the initial corpus without Ableton. Supersedes the Phase 6/7 Faust path; reworks the Phase 5 app onto the 4-op model. Phases 8+.

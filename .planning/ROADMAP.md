# Roadmap: Apollo v2.0 — Call-and-Response v1

## Overview

Four phases take Apollo from an empty repo to a demonstrably improving active-learning loop. Phase 1 builds the symbolic pipeline — tokenizer, data ingest, mel extraction, and error handling — so that any pair folder can be converted to tensors. Phase 2 adds the model and trains it on mock data to confirm the architecture is wired correctly before a single real pair is authored. Phase 3 is the human work: authoring ≥30 Ableton pairs and standing up inference so generated responses can actually be heard. Phase 4 closes the loop — scoring rubric, per-iteration tracking, and the ship gate that defines "done."

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Tokenizer & Ingest** - Tokenizer, data pipeline, mel extraction, held-out split
- [x] **Phase 2: Model & Training** - Mel encoder, transformer, masked loss, smoke train, checkpoints
- [x] **Phase 3: Corpus & Inference** - Author ≥30 pairs, generate.py, sampling controls (code shipped; corpus authoring pending)
- [x] **Phase 4: Evaluation Loop** - Scoring rubric, grading workflow, iteration tracking, ship gate
- [ ] **Phase 5: Local App & In-Browser Synth** - Local-only user app: drag-drop pairs, in-browser FM synth, train triggers, call→response flow
- [ ] **Phase 6: Synth-Independent Corpus Rendering** - Single source-of-truth FM spec + headless Python/Faust 3-op renderer that produces `call.wav` deterministically with no Ableton (prerequisite for corpus authoring; Phase 5's browser synth consumes the same spec)

## Phase Details

### Phase 1: Tokenizer & Ingest
**Goal**: The pipeline can ingest any `data/pairs/NNN/` folder and produce training-ready tensors
**Depends on**: Nothing (first phase)
**Requirements**: TOK-01, TOK-02, TOK-03, TOK-04, TOK-05, DATA-01, DATA-02, DATA-03, DATA-04, COND-01, COND-04
**Success Criteria** (what must be TRUE):
  1. A MIDI file round-trips through the tokenizer and decodes back with pitches, velocities, and onsets preserved within quantization tolerance
  2. Running the ingest script over a folder of mock pairs produces tokenized tensors and mel-spectrogram tensors with no silent failures
  3. Any pair with a missing or malformed `call.wav` causes the pipeline to report the offending pair and abort — not silently skip
  4. The held-out split is deterministic: the same 20% of pairs are held out on every run regardless of authoring order
  5. The vocab layout includes BOS, EOS, SEP, and contiguous reserved ranges for future pitch bend / mod wheel / CC tokens
**Plans**: 5 plans
- [x] 01-01-PLAN.md — Project scaffold + Vocab dataclass + duration bins + IngestError + vocab-layout test
- [x] 01-02-PLAN.md — Tokenizer encoder + decoder + round-trip test (TOK-05)
- [x] 01-03-PLAN.md — MelExtractor (torchaudio Resample + MelSpectrogram, (96,128) log-mel) + tests
- [x] 01-04-PLAN.md — Pair discovery + MIDI load + hash split + artifact format + CLI script
- [x] 01-05-PLAN.md — Mock pair generator + end-to-end smoke test + error-handling tests (CLI exit codes)

### Phase 2: Model & Training
**Goal**: The model trains from scratch on mock pairs, hits the smoke-train accuracy bar, and saves a complete checkpoint artifact
**Depends on**: Phase 1
**Requirements**: COND-02, COND-03, TRAIN-01, TRAIN-02, TRAIN-03, TRAIN-04, TRAIN-05, TRAIN-06
**Success Criteria** (what must be TRUE):
  1. A smoke train on ≥10 mock pairs reaches >95% next-token type-accuracy on the response side, confirming the architecture is wired correctly
  2. Loss is visibly lower on response tokens than on call tokens, confirming the mask is applied correctly
  3. Training completes without error on the local MPS device with no Modal/cloud dependency
  4. A checkpoint saved under `models/` contains model weights, mel encoder weights, and tokenizer config in a single artifact
**Plans**: 5 plans
- [x] 02-01-PLAN.md — MelEncoder (CNN mel-to-embedding) + tests (COND-02, COND-03)
- [x] 02-02-PLAN.md — ApolloModel (decoder-only transformer w/ MEL prefix) + tests (TRAIN-01, TRAIN-03, TRAIN-05)
- [x] 02-03-PLAN.md — ApolloDataset + collate_fn (TRAIN-01 sequence packing) + tests
- [x] 02-04-PLAN.md — Masked CE loss, type-accuracy metric, train_epoch + tests (TRAIN-02, TRAIN-03, TRAIN-05)
- [x] 02-05-PLAN.md — Smoke-train CLI + checkpoint save/load + >0.95 type-acc gate (TRAIN-04, TRAIN-06)

### Phase 3: Corpus & Inference
**Goal**: ≥30 authored pairs exist and `generate.py` can produce a response MIDI from a call pair
**Depends on**: Phase 2
**Requirements**: DATA-05, INFER-01, INFER-02, INFER-03, INFER-04
**Success Criteria** (what must be TRUE):
  1. At least 30 call/response pairs are authored in Ableton and present in `data/pairs/` in the correct folder layout
  2. Running `generate.py` with a `call.mid` + `call.wav` produces a `response.mid` that is valid MIDI and playable in Ableton
  3. Response length, temperature, and top-k are configurable at the command line without code changes
  4. Sampling N responses for a single call produces N distinct `response.mid` files the user can audition
**Plans**: 3 plans
- [ ] 03-01-PLAN.md — data/pairs/ directory stub + CORPUS-CONVENTIONS.md authoring guide (DATA-05)
- [ ] 03-02-PLAN.md — generate.py autoregressive inference CLI + tests (INFER-01..04)
- [ ] 03-03-PLAN.md — train.py real-corpus training CLI with OneCycleLR + held-out logging + tests

### Phase 4: Evaluation Loop
**Goal**: Users can score held-out pairs per iteration and confirm consecutive improvements — the ship gate is reachable
**Depends on**: Phase 3
**Requirements**: EVAL-01, EVAL-02, EVAL-03, EVAL-04, EVAL-05
**Success Criteria** (what must be TRUE):
  1. A listen-test rubric exists with a "call-response fit" (1–5) dimension plus at least one other musical-quality dimension, documented and usable without explanation
  2. The grading workflow plays call then response back-to-back per held-out pair so the user can score without manual file management
  3. Scores from each training run are persisted to CSV/JSON and the delta from the previous run is surfaced automatically
  4. v1 ships only after two consecutive iteration rounds both show improvement in mean held-out call-response-fit score
**Plans**: TBD

### Phase 5: Local App & In-Browser Synth
**Goal**: A purely local, user-facing app that lets a user build a corpus by drag-and-drop, render call/response audio in-browser (no Ableton required), trigger training, and upload a call to get a generated response back — closing the whole loop in one app. **Primary purpose: a public demonstration front-end** that shows Apollo training and generating locally to anyone, regardless of whether they own Ableton.
**Depends on**: Phase 2 (model) + Phase 3 *code* (`train.py`, `generate.py`) — both shipped. Does **not** depend on corpus completion or the Phase 4 ship gate.
**Parallelizable**: Yes. This phase runs as a parallel workstream alongside ongoing corpus authoring / model tuning (Phase 3 corpus work, Phase 4 iterations). It is unblocked now and demos against whatever checkpoint currently exists.
**Requirements**: TBD (new requirements to be authored at plan time — candidate APP-01..NN)
**Success Criteria** (what must be TRUE):
  1. **Local-only.** The app runs entirely on the user's machine (local server + browser, or fully offline). No data leaves the device; no cloud calls required to author, train, or infer.
  2. **Drag-and-drop pair ingest.** A user can drag MIDI (and/or play/record) call+response into the app and it lands as a valid `data/pairs/NNN/` folder, validated against `CORPUS-CONVENTIONS.md` with clear inline errors.
  3. **Corpus-growth flow.** The UI actively encourages volume — visible pair count vs. the ≥30 ship-gate target, progress/streak affordances, and a frictionless "add another" loop.
  4. **In-browser synthesizer.** An Operator-style FM synth runs in the browser (Web Audio API, 4 operators with selectable algorithms + envelopes) and renders `call.wav` locally, removing the manual Ableton bounce. Tone.js `FMSynth` is 2-operator only, so a custom Web Audio operator graph is the faithful path; Tone.js may scaffold simpler cases.
  5. **Training triggers.** A manual "Train" button kicks off `train.py`; a setting toggles auto-retrain-on-every-pair-upload. Training status/progress is surfaced in the UI and never blocks the authoring flow.
  6. **Configurable response storage.** The user can configure where generated responses are written (a chosen local directory), and produced responses are listed/auditionable in-app.
  7. **Call→response flow.** A user uploads (or plays) a call, the app renders its audio via the in-browser synth, runs inference, and returns a playable `response.mid` (auditioned in-app via the same synth).
**Research note**: In-browser Operator alternative — Web Audio API `OscillatorNode`×4 wired per Operator's algorithm set + `GainNode` ADSR is the faithful, dependency-light approach; Tone.js (`FMSynth`) is convenient but only 2-operator. Faust or Rust→WASM are heavier options if performance/algorithm fidelity demands it.
**Cross-phase note (added 2026-06-02)**: Phase 6 owns the **single source-of-truth FM spec** (param schema + algorithm set + envelope semantics). Phase 5's in-browser synth must implement *that* spec so app-rendered and corpus-rendered `call.wav` stay sonically matched (train/serve consistency). Reconcile op count: v1 spec is **3-op** (per `synth-independence-decision`); Phase 5 SC#4 currently says 4-op — align to the shared spec at plan time.
**Plans**: TBD

### Phase 6: Synth-Independent Corpus Rendering
**Goal**: Replace the manual Ableton/Operator `call.wav` bounce with an **owned FM synth rendered headlessly in Python**. Define a single source-of-truth FM **spec** (parameter schema + algorithm set + envelope semantics), implement a deterministic **3-operator** Faust renderer (via DawDreamer) that turns a per-pair FM-param manifest + `call.mid` into `call.wav`, and wire it so the **same engine renders inference-time calls** — eliminating Ableton from both training and serving with no domain gap. Operator's *sound* is explicitly not cloned (see `.planning/notes/synth-independence-decision.md`); only a controllable FM family is provided.
**Depends on**: Phase 1 (COND-01 mel contract — already shipped, consumes `call.wav` unchanged). No dependency on Phase 4/5.
**Blocks**: DATA-05 (real corpus authoring) — pairs can't be authored without a way to render `call.wav`. Sequence before corpus authoring resumes.
**Relationship to Phase 5**: Phase 6 defines the shared FM spec; Phase 5's browser synth (SC#4) is retargeted to consume it so both renderers produce matching audio. The two engines are validated against each other.
**Requirements**: DATA-06 (new). Candidate additional reqs (author at plan time): per-pair FM-param manifest format; renderer determinism guarantee; headroom/normalization before PCM write.
**Success Criteria** (what must be TRUE):
  1. **No Ableton.** A pair's `call.wav` is produced entirely in Python from `call.mid` + an FM-param manifest; Ableton/Operator are not in the loop for training or inference.
  2. **Single FM spec.** Param schema + algorithm set + envelope semantics live in one place, versioned, consumed by the Python renderer (and, downstream, the Phase 5 browser synth).
  3. **Deterministic.** Re-rendering the same manifest + MIDI is bit-identical (reproducible training data).
  4. **Drop-in conditioning.** Rendered audio feeds the existing `MelExtractor` (COND-01) unchanged to the `(96,128)` contract; no pipeline change.
  5. **Hand-authorable.** Per-pair timbre is a small, documented FM-param manifest (JSON/code) a human authors by hand — no synth UI required for v1.
  6. **Train/serve parity.** Inference-time call rendering uses the same engine + manifest format as corpus rendering.
**Research note**: Validated by spikes 001 (`dawdreamer` arm64 wheel, deterministic Faust FM render) and 002 (FM audio → exact COND-01 mel, timbre-discriminable). Build gotchas captured in the `spike-findings-apollo` skill: poly Faust params via integer index not path; clip/headroom before PCM; benign `undefined symbol: effect` warning.
**Plans**: 3 plans
- [x] 06-01-PLAN.md — Add dawdreamer dep (verify single-venv coexistence) + FM spec source-of-truth (spec.py) + manifest validator (manifest.py) (DATA-06)
- [x] 06-02-PLAN.md — Deterministic 3-op DawDreamer/Faust renderer (render.py) + render_corpus CLI + determinism/mel/timbre/parity tests (DATA-06)
- [ ] 06-03-PLAN.md — generate.py train/serve parity wiring (render from call_fm.json) + de-Ableton CORPUS-CONVENTIONS/REQUIREMENTS reconcile + gitignore (DATA-06)

## Progress

**Execution Order:**
Phases 1 → 2 → 3 → 4 execute in numeric order. **Phase 5 runs in parallel** — it depends only on shipped code (Phase 2 model + Phase 3 CLIs), not on corpus completion, so it can be built as a separate workstream while corpus tuning continues. **Phase 6 is a prerequisite for DATA-05** (real corpus authoring) — it must land before pair authoring resumes, since `call.wav` can no longer come from Ableton. Phase 6 also defines the FM spec that Phase 5's browser synth consumes.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Tokenizer & Ingest | 5/5 | Complete | 2026-05-19 |
| 2. Model & Training | 5/5 | Complete | 2026-05-20 |
| 3. Corpus & Inference | 0/3 | Not started | - |
| 4. Evaluation Loop | 0/TBD | Not started | - |
| 5. Local App & In-Browser Synth | 0/TBD | Not started | - |
| 6. Synth-Independent Corpus Rendering | 1/3 | In progress | - |

## Backlog

### Phase 999.3: Cross-Synth Parameter Mapping (BACKLOG)

**Goal:** Extend Apollo's preset generation head beyond Operator to other synth instruments — starting with native Ableton instruments (Analog, Wavetable, Drift), then third-party VSTs. The model outputs a response preset in whatever instrument the user is working with, not just Operator.
**Motivation:** Apollo's preset-as-transformation approach (999.1) learns parameter mutations within Operator's schema. Extending this to other instruments requires either (a) manual ontology mapping — research each instrument's manual, define parameter analogs to Operator, translate the learned transformation into the target dialect — or (b) a learned cross-synth timbral embedding where audio bridges parameter spaces across instruments. The latter may be a genuinely new field: no existing system handles arbitrary synth plugin parameter mapping at the semantic level.
**Prerequisites:** 999.1 (FM patch generation head) complete; Operator parameter schema validated; `.adg` corpus capture workflow established.
**Requirements:** TBD
**Plans:** 0 plans
- [ ] TBD (promote with /gsd-review-backlog when ready)

### Phase 999.2: Synthesis-Level Rhythmic Response (BACKLOG)

**Goal:** Close the asymmetry between call and response rhythmic channels. In v1, calls can carry timbral rhythm via LFO/envelope (a filter LFO on a held note creates a perceived pulse), but the model can only answer with MIDI note events. A future milestone should either (a) extend the response channel to include synthesis parameter suggestions (LFO rate, envelope shape) or (b) augment the tokenizer with CC/mod-wheel tokens that can proxy synthesis-level rhythm.
**Motivation:** Operator FM patches frequently use LFOs for rhythmic expression. Constraining corpus authoring to note-event rhythm (the v1 workaround) limits musical range and is unnatural for FM sound design.
**Prerequisites:** Phase 4 complete; at least one corpus iteration showing clear note-rhythm call-response fit; Phase 999.1 (FM patch generation head) is a natural prerequisite.
**Requirements:** TBD
**Plans:** 0 plans
- [ ] TBD (promote with /gsd-review-backlog when ready)

### Phase 999.1: FM Patch Generation Head (BACKLOG)

**Goal:** Extend the model to suggest Operator FM patch parameters alongside response MIDI — the model outputs both notes *and* a timbre suggestion, giving complete call-and-response including sound design.
**Motivation:** The call preset is already known (user authored it). The response preset is a *transformation* of the call preset — not an inverse synthesis problem, but a direct parameter-to-parameter mapping. The model learns what FM mutations constitute a musical response: flip an algorithm, change coarse tuning on a carrier, swap a modulator waveform. Training signal is (call_params, response_params) pairs from corpus; no audio reconstruction loss required. Corpus change: capture `call_preset.adg` + `response_preset.adg` per pair (one Ableton export step per track). Inference output: `response.mid` + `response_preset.adg`, directly loadable in Ableton Operator.
**Prerequisites:** v1 evaluation loop complete (Phase 4); corpus authoring extended to capture `.adg` preset exports per pair; Operator parameter schema defined (~40–60 meaningful params).
**Requirements:** TBD
**Plans:** 0 plans
- [ ] TBD (promote with /gsd-review-backlog when ready)

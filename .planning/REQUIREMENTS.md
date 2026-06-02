# Requirements: Apollo

**Defined:** 2026-05-19
**Core Value:** Given a short MIDI call played through an Operator preset, the model produces a response that feels like the user responding to themselves — and the active-learning loop demonstrably improves it over consecutive iterations.

## v1 Requirements

### Corpus (DATA)

- [x] **DATA-01**: User can author and export call/response pairs in Ableton with both tracks running Operator (potentially different presets per pair) — *SUPERSEDED by DATA-06: the Ableton/Operator authoring premise is replaced by the hand-authored FM-manifest workflow (`call_fm.json`); pairs are no longer authored in Ableton. See `.planning/notes/synth-independence-decision.md`.*
- [x] **DATA-02**: Each pair lives at `data/pairs/NNN/` (NNN zero-padded, sequential). Authored files: `call.mid`, `call_fm.json` (hand-authored FM-parameter manifest), `response.mid`. `call.wav` is a **derived** render (no longer a manual Ableton bounce) — *SUPERSEDED by DATA-06; the manual-bounce premise is replaced by deterministic rendering from `call_fm.json`.*
- [x] **DATA-03**: An ingestion pipeline reads `data/pairs/*/` and tokenizes pairs into training tensors (MIDI tokens + mel features per pair)
- [x] **DATA-04**: The pipeline reserves 20% of pairs as a held-out evaluation split, deterministically (same split every run)
- [ ] **DATA-05**: Corpus reaches ≥30 authored pairs before first real training run
- [x] **DATA-06**: Apollo renders a pair's `call.wav` **deterministically** from a per-pair FM parameter manifest using a headless, **no-Ableton** FM synth (DawDreamer + Faust; 3-operator for v1), producing audio that feeds COND-01 unchanged. The same engine renders inference-time calls so training and serving share one renderer (no domain gap). *Supersedes the manual-Ableton-bounce premise of DATA-01/DATA-02; see `.planning/notes/synth-independence-decision.md`.*

### Tokenizer (TOK)

- [x] **TOK-01**: A monophonic MIDI event tokenizer encodes pitch + velocity + timing + duration as discrete tokens
- [x] **TOK-02**: Time and duration use quantized-grid bins (coarse resolution suitable for grid-locked authoring)
- [x] **TOK-03**: The vocab includes BOS, EOS, and SEP special tokens with SEP placed between call and response in training samples
- [x] **TOK-04**: The vocab layout reserves contiguous ranges (or a versioned offset scheme) for later pitch bend / mod wheel / CC tokens, so adding them does not invalidate existing checkpoints
- [x] **TOK-05**: Round-trip test: a tokenizer applied to mock pairs decodes back to MIDI semantically equivalent to the input (pitches, velocities, onsets preserved within quantization tolerance)

### Audio Conditioning (COND)

- [x] **COND-01**: A mel-feature extractor reads `call.wav` and produces a fixed-shape mel-spectrogram tensor at a documented sample rate / hop / n_mels
- [x] **COND-02**: A small mel encoder (CNN or equivalent) compresses the mel tensor into a conditioning embedding fed alongside MIDI tokens
- [x] **COND-03**: The mel encoder is part of the trained model graph (jointly trained, not frozen pretrained)
- [x] **COND-04**: If a pair's `call.wav` is missing or malformed, the pipeline reports the offending pair and aborts (no silent skipping)

### Training (TRAIN)

- [x] **TRAIN-01**: Training samples pack as `[BOS, call_tokens, SEP, response_tokens, EOS]` with the SEP boundary explicit
- [x] **TRAIN-02**: Cross-entropy loss is **masked to response tokens only** — the model is not penalized for the call side
- [x] **TRAIN-03**: Model is trained from scratch (random init); no warm-start from any prior checkpoint
- [x] **TRAIN-04**: A smoke-train on ≥10 mock pairs reaches >95% next-token type-accuracy on the response side (sanity check, structurally valid output)
- [x] **TRAIN-05**: Training runs locally on MPS (Apple Silicon) in a reasonable wall-clock for the small corpus (no Modal/cloud dependency)
- [x] **TRAIN-06**: Checkpoints save model state + mel encoder + tokenizer config in a single artifact under `models/`

### Inference (INFER)

- [ ] **INFER-01**: `generate.py` accepts a path to a `call.mid` + `call.wav` pair and emits a `response.mid`
- [ ] **INFER-02**: Response length is configurable (max events or max seconds budget)
- [ ] **INFER-03**: Sampling supports temperature and top-k controls
- [ ] **INFER-04**: Optional: sample N responses per call to let the user pick a preferred one

### Evaluation (EVAL)

- [x] **EVAL-01**: A listen-test rubric exists with "call-response fit" (1–5) as one dimension, plus other musical-quality dimensions
- [x] **EVAL-02**: A grading workflow plays call → response back-to-back per cell so the user can score
- [x] **EVAL-03**: Held-out scoring is persisted per run (CSV/JSON) so deltas across iterations are visible
- [x] **EVAL-04**: A tracking surface (script or doc) shows score-per-iteration deltas across consecutive training runs
- [ ] **EVAL-05**: v1 ships only when two consecutive iteration rounds both improve mean held-out call-response-fit score *(blocked on real corpus iterations — see DATA-05)*

### Synthesis (SYNTH)

- [x] **SYNTH-01**: The owned FM synth supports an optional per-patch **LFO** (rate, depth, waveform, target) authored in `call_fm.json`, rendered **deterministically** by the shared engine and documented for the Phase 5 browser synth. The FM spec is versioned to **v1.1**; a v1.0 manifest (no `lfo` block) renders **bit-identically** to the Phase 6 output (no corpus invalidation) and the loader accepts both versions. Rendered audio still feeds `MelExtractor` (COND-01) unchanged. *(Promotes the call-side expression mechanism of backlog 999.2 — the LFO-driven rhythmic/timbral motion FM is known for.)*

### Local App (APP) — Phase 5

Authored 2026-06-02 at plan time (candidate APP-* from ROADMAP §Phase 5). Each maps to ≥1 Phase 5 success criterion (SC#1–SC#7). The synth targets the shared 3-op v1.1 FM spec (D-20); the in-browser synth is audition/preview only (D-15) — canonical `call.wav` is always server-rendered (D-11).

- [ ] **APP-01**: `apollo/app/` Flask app launches with `python -m apollo.app`, binds `127.0.0.1` (never `0.0.0.0`, `debug=False`), opens the browser to the dashboard. *(SC#1; D-01, D-04)*
- [ ] **APP-02**: Dashboard shows three equal-weight tiles — Corpus (pair count at Display size + progress vs 30), Training (status + CTA), Generate (CTA + recent responses) — with a persistent local-only trust badge. *(SC#1, SC#3; UI-SPEC Layout)*
- [ ] **APP-03**: Corpus drag-drop ingest: upload `call.mid` + `call_fm.json`, validated server-side via `apollo.synth.load_manifest` + `apollo.ingest.load_notes` (same errors as the CLI), written to `data/pairs/NNN/` with `call.wav` rendered in-process; invalid input returns the IngestError reason and writes no orphan dir. *(SC#2; D-09, D-13, D-14)*
- [ ] **APP-04**: FM patch editor: algorithm selector + per-operator ratio/level/ADSR + optional collapsible LFO section, all client-validated against `spec_constants.js` BOUNDS; saves a `load_manifest`-valid `call_fm.json`. *(SC#4, SC#7; D-18, D-19, D-20)*
- [ ] **APP-05**: Browser FM synth: hand-rolled 3-op v1.1 Web Audio graph (no Tone.js), per-algorithm topology + `op_level*freq` mod scaling from `spec.py`, LFO tremolo/vibrato per `CORPUS-CONVENTIONS.md` formulas. Audition only — never canonical. *(SC#4; D-15, D-16, D-19, D-20)*
- [ ] **APP-06**: Patch-editor live preview: editing any control immediately previews a test note through the browser synth. *(SC#4; D-16, D-18)*
- [ ] **APP-07**: Training triggers: manual "Train model" button + auto-retrain-on-upload toggle with server-side debounce (one run per bulk drop); `POST /train` subprocesses `apollo.scripts.train` (full retrain from scratch). *(SC#5; D-02, D-03, D-05, D-06)*
- [ ] **APP-08**: Live training visibility: progress bar (epoch/total) + loss-over-epochs canvas curve (train + held), via ~1s polling of `GET /status`. *(SC#5; D-07, D-08)*
- [ ] **APP-09**: Call→response flow: upload `call.mid` + author patch → `POST /generate` subprocesses `apollo.scripts.generate` → `response.mid` written to the configurable store and auditioned through the call's own patch (D-17). *(SC#7; D-02, D-12, D-17)*
- [ ] **APP-10**: Response audition: server exposes `GET /midi/<nnn>/<file>` returning note JSON; the browser plays call/response MIDI through the same FM synth (no client MIDI parser). *(SC#7; D-16, D-17)*
- [ ] **APP-11**: Corpus pair audition: each pair's `call.mid` is auditionable in the corpus list via the same MIDI-to-JSON + browser synth. *(SC#3; D-16)*
- [ ] **APP-12**: Configurable response storage: an in-app setting persists the response output directory (default `data/responses/`); responses are listed and auditionable in-app. *(SC#6; D-12)*
- [ ] **APP-13**: Bundled FM presets: ≥3 starter `call_fm.json` presets covering different algorithms/timbres, loadable in the patch editor as starting points. *(SC#4; D-18)*

## v2 Requirements

Deferred to a later milestone. Tracked here so they don't get lost.

### Expression (EXPR)

- **EXPR-01**: Pitch-bend tokens added to vocab (offset reserved in TOK-04), tokenizer encodes/decodes them, training corpus includes pitch-bend-rich pairs
- **EXPR-02**: Mod-wheel / CC tokens added to vocab; user authors CC automation in call and response
- **EXPR-03**: Aftertouch and other expressive controllers

### Timing (TIME)

- **TIME-01**: Groove / humanized / off-grid timing supported by widening the time-bin resolution (or moving to a hybrid bin+offset scheme)
- **TIME-02**: Tempo variations across pairs (currently assumed constant)

### Real-time (RT)

- **RT-01**: Max for Live device wraps the model for in-Ableton call→response
- **RT-02**: Live audio capture of the call (not just `.mid` file)
- **RT-03**: Sub-50ms latency call-end → first response note

### Capacity (CAP)

- **CAP-01**: Polyphonic call/response (chords, overlapping voices)
- **CAP-02**: Longer phrases (>2 sec, >6 notes per side)
- **CAP-03**: Multi-bar pairs with internal structure

## Out of Scope

| Feature | Reason |
|---------|--------|
| Pretraining on MAESTRO or other piano corpora | Piano priors (pedal-active rate, piano dynamics envelope) actively conflict with FM/Operator material; prior code lives on `deprecated` branch as reference only |
| Non-Operator instruments | v1 timbre space constrained to one FM family so mel-conditioning is learnable on a small corpus |
| Model produces audio output (waveform / codec tokens) | Symbolic MIDI output is sufficient to validate the call→response idea; audio output is scope explosion |
| Relationship-mode labels (call-back / answer / continuation) | Zero labeling overhead; "Jerald-shape" is the implicit target across modes |
| Cloud / Modal training | Model + corpus are small enough to train locally on MPS |
| Pretrained mel encoders (e.g. AudioMAE, CLAP) | First version trains the mel encoder jointly so it specializes to the Operator-FM spectral family on this corpus |
| Multi-instrument training (e.g. piano + bass + drums) | v1 is solo Operator only; multi-track ensemble is a separate problem class |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| DATA-01 | Phase 1: Tokenizer & Ingest | Done (01-05) — superseded by DATA-06 (Phase 6) |
| DATA-02 | Phase 1: Tokenizer & Ingest | Done (01-04) — superseded by DATA-06 (Phase 6) |
| DATA-03 | Phase 1: Tokenizer & Ingest | Done (01-04) |
| DATA-04 | Phase 1: Tokenizer & Ingest | Done (01-04) |
| DATA-05 | Phase 3: Corpus & Inference | Pending (real corpus authoring) |
| DATA-06 | Phase 6: Synth-Independent Corpus Rendering | Done (06-01 spec/manifest, 06-02 renderer/CLI, 06-03 inference parity + doc reconciliation) |
| SYNTH-01 | Phase 7: Synth Automation (LFO) | Complete (2026-06-02 — v1.1 LFO spec, validation, render, tests, doc; verified 6/6) |
| TOK-01 | Phase 1: Tokenizer & Ingest | Done (01-02) |
| TOK-02 | Phase 1: Tokenizer & Ingest | Done (01-02) |
| TOK-03 | Phase 1: Tokenizer & Ingest | Done (01-01) |
| TOK-04 | Phase 1: Tokenizer & Ingest | Done (01-01) |
| TOK-05 | Phase 1: Tokenizer & Ingest | Done (01-05) |
| COND-01 | Phase 1: Tokenizer & Ingest | Done (01-03) |
| COND-02 | Phase 2: Model & Training | Done (02-01) |
| COND-03 | Phase 2: Model & Training | Done (02-01) |
| COND-04 | Phase 1: Tokenizer & Ingest | Done (01-05) |
| TRAIN-01 | Phase 2: Model & Training | Done (02-03) |
| TRAIN-02 | Phase 2: Model & Training | Done (02-04) |
| TRAIN-03 | Phase 2: Model & Training | Done (02-04) |
| TRAIN-04 | Phase 2: Model & Training | Done (02-05) |
| TRAIN-05 | Phase 2: Model & Training | Done (02-04) |
| TRAIN-06 | Phase 2: Model & Training | Done (02-05) |
| INFER-01 | Phase 3: Corpus & Inference | Done (03-02) |
| INFER-02 | Phase 3: Corpus & Inference | Done (03-02) |
| INFER-03 | Phase 3: Corpus & Inference | Done (03-02) |
| INFER-04 | Phase 3: Corpus & Inference | Done (03-02) |
| EVAL-01 | Phase 4: Evaluation Loop | Done (04-01) |
| EVAL-02 | Phase 4: Evaluation Loop | Done (04-04) |
| EVAL-03 | Phase 4: Evaluation Loop | Done (04-02) |
| EVAL-04 | Phase 4: Evaluation Loop | Done (04-03) |
| EVAL-05 | Phase 4: Evaluation Loop | Pending (real corpus iterations) |
| APP-01 | Phase 5: Local App & In-Browser Synth | Planned (05-01) |
| APP-02 | Phase 5: Local App & In-Browser Synth | Planned (05-01) |
| APP-03 | Phase 5: Local App & In-Browser Synth | Planned (05-03) |
| APP-04 | Phase 5: Local App & In-Browser Synth | Planned (05-04) |
| APP-05 | Phase 5: Local App & In-Browser Synth | Planned (05-02) |
| APP-06 | Phase 5: Local App & In-Browser Synth | Planned (05-04) |
| APP-07 | Phase 5: Local App & In-Browser Synth | Planned (05-03) |
| APP-08 | Phase 5: Local App & In-Browser Synth | Planned (05-03) |
| APP-09 | Phase 5: Local App & In-Browser Synth | Planned (05-04) |
| APP-10 | Phase 5: Local App & In-Browser Synth | Planned (05-02) |
| APP-11 | Phase 5: Local App & In-Browser Synth | Planned (05-02) |
| APP-12 | Phase 5: Local App & In-Browser Synth | Planned (05-03) |
| APP-13 | Phase 5: Local App & In-Browser Synth | Planned (05-04) |

**Coverage:**
- v1 requirements: 42 total (29 original + SYNTH-01 + DATA-06 already counted; +13 APP)
- Mapped to phases: 42
- Unmapped: 0 ✓
- Phase 5 (APP-01..APP-13): all 13 mapped across plans 05-01..05-04; every SC#1–SC#7 covered.

---
*Requirements defined: 2026-05-19*

# Requirements: Apollo

**Defined:** 2026-05-19
**Core Value:** Given a short MIDI call played through an Operator preset, the model produces a response that feels like the user responding to themselves — and the active-learning loop demonstrably improves it over consecutive iterations.

## v1 Requirements

### Corpus (DATA)

- [ ] **DATA-01**: User can author and export call/response pairs in Ableton with both tracks running Operator (potentially different presets per pair)
- [ ] **DATA-02**: Each pair lives at `data/pairs/NNN/` with three files: `call.mid`, `call.wav` (manual Ableton bounce), `response.mid` (NNN zero-padded, sequential)
- [ ] **DATA-03**: An ingestion pipeline reads `data/pairs/*/` and tokenizes pairs into training tensors (MIDI tokens + mel features per pair)
- [ ] **DATA-04**: The pipeline reserves 20% of pairs as a held-out evaluation split, deterministically (same split every run)
- [ ] **DATA-05**: Corpus reaches ≥30 authored pairs before first real training run

### Tokenizer (TOK)

- [ ] **TOK-01**: A monophonic MIDI event tokenizer encodes pitch + velocity + timing + duration as discrete tokens
- [ ] **TOK-02**: Time and duration use quantized-grid bins (coarse resolution suitable for grid-locked authoring)
- [ ] **TOK-03**: The vocab includes BOS, EOS, and SEP special tokens with SEP placed between call and response in training samples
- [ ] **TOK-04**: The vocab layout reserves contiguous ranges (or a versioned offset scheme) for later pitch bend / mod wheel / CC tokens, so adding them does not invalidate existing checkpoints
- [ ] **TOK-05**: Round-trip test: a tokenizer applied to mock pairs decodes back to MIDI semantically equivalent to the input (pitches, velocities, onsets preserved within quantization tolerance)

### Audio Conditioning (COND)

- [ ] **COND-01**: A mel-feature extractor reads `call.wav` and produces a fixed-shape mel-spectrogram tensor at a documented sample rate / hop / n_mels
- [ ] **COND-02**: A small mel encoder (CNN or equivalent) compresses the mel tensor into a conditioning embedding fed alongside MIDI tokens
- [ ] **COND-03**: The mel encoder is part of the trained model graph (jointly trained, not frozen pretrained)
- [ ] **COND-04**: If a pair's `call.wav` is missing or malformed, the pipeline reports the offending pair and aborts (no silent skipping)

### Training (TRAIN)

- [ ] **TRAIN-01**: Training samples pack as `[BOS, call_tokens, SEP, response_tokens, EOS]` with the SEP boundary explicit
- [ ] **TRAIN-02**: Cross-entropy loss is **masked to response tokens only** — the model is not penalized for the call side
- [ ] **TRAIN-03**: Model is trained from scratch (random init); no warm-start from any prior checkpoint
- [ ] **TRAIN-04**: A smoke-train on ≥10 mock pairs reaches >95% next-token type-accuracy on the response side (sanity check, structurally valid output)
- [ ] **TRAIN-05**: Training runs locally on MPS (Apple Silicon) in a reasonable wall-clock for the small corpus (no Modal/cloud dependency)
- [ ] **TRAIN-06**: Checkpoints save model state + mel encoder + tokenizer config in a single artifact under `models/`

### Inference (INFER)

- [ ] **INFER-01**: `generate.py` accepts a path to a `call.mid` + `call.wav` pair and emits a `response.mid`
- [ ] **INFER-02**: Response length is configurable (max events or max seconds budget)
- [ ] **INFER-03**: Sampling supports temperature and top-k controls
- [ ] **INFER-04**: Optional: sample N responses per call to let the user pick a preferred one

### Evaluation (EVAL)

- [ ] **EVAL-01**: A listen-test rubric exists with "call-response fit" (1–5) as one dimension, plus other musical-quality dimensions
- [ ] **EVAL-02**: A grading workflow plays call → response back-to-back per cell so the user can score
- [ ] **EVAL-03**: Held-out scoring is persisted per run (CSV/JSON) so deltas across iterations are visible
- [ ] **EVAL-04**: A tracking surface (script or doc) shows score-per-iteration deltas across consecutive training runs
- [ ] **EVAL-05**: v1 ships only when two consecutive iteration rounds both improve mean held-out call-response-fit score

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

Empty until roadmap is created.

| Requirement | Phase | Status |
|-------------|-------|--------|
| (populated by roadmapper) | | |

**Coverage:**
- v1 requirements: 29 total
- Mapped to phases: 0 (pending roadmap)
- Unmapped: 29 ⚠️ (expected until roadmap commits)

---
*Requirements defined: 2026-05-19*
*Last updated: 2026-05-19 after initial definition*

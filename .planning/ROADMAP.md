# Roadmap: Apollo v2.0 — Call-and-Response v1

## Overview

Four phases take Apollo from an empty repo to a demonstrably improving active-learning loop. Phase 1 builds the symbolic pipeline — tokenizer, data ingest, mel extraction, and error handling — so that any pair folder can be converted to tensors. Phase 2 adds the model and trains it on mock data to confirm the architecture is wired correctly before a single real pair is authored. Phase 3 is the human work: authoring ≥30 Ableton pairs and standing up inference so generated responses can actually be heard. Phase 4 closes the loop — scoring rubric, per-iteration tracking, and the ship gate that defines "done."

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Tokenizer & Ingest** - Tokenizer, data pipeline, mel extraction, held-out split
- [ ] **Phase 2: Model & Training** - Mel encoder, transformer, masked loss, smoke train, checkpoints
- [ ] **Phase 3: Corpus & Inference** - Author ≥30 pairs, generate.py, sampling controls
- [ ] **Phase 4: Evaluation Loop** - Scoring rubric, grading workflow, iteration tracking, ship gate

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
- [ ] 01-01-PLAN.md — Project scaffold + Vocab dataclass + duration bins + IngestError + vocab-layout test
- [ ] 01-02-PLAN.md — Tokenizer encoder + decoder + round-trip test (TOK-05)
- [ ] 01-03-PLAN.md — MelExtractor (torchaudio Resample + MelSpectrogram, (96,128) log-mel) + tests
- [ ] 01-04-PLAN.md — Pair discovery + MIDI load + hash split + artifact format + CLI script
- [ ] 01-05-PLAN.md — Mock pair generator + end-to-end smoke test + error-handling tests (CLI exit codes)

### Phase 2: Model & Training
**Goal**: The model trains from scratch on mock pairs, hits the smoke-train accuracy bar, and saves a complete checkpoint artifact
**Depends on**: Phase 1
**Requirements**: COND-02, COND-03, TRAIN-01, TRAIN-02, TRAIN-03, TRAIN-04, TRAIN-05, TRAIN-06
**Success Criteria** (what must be TRUE):
  1. A smoke train on ≥10 mock pairs reaches >95% next-token type-accuracy on the response side, confirming the architecture is wired correctly
  2. Loss is visibly lower on response tokens than on call tokens, confirming the mask is applied correctly
  3. Training completes without error on the local MPS device with no Modal/cloud dependency
  4. A checkpoint saved under `models/` contains model weights, mel encoder weights, and tokenizer config in a single artifact
**Plans**: TBD

### Phase 3: Corpus & Inference
**Goal**: ≥30 authored pairs exist and `generate.py` can produce a response MIDI from a call pair
**Depends on**: Phase 2
**Requirements**: DATA-05, INFER-01, INFER-02, INFER-03, INFER-04
**Success Criteria** (what must be TRUE):
  1. At least 30 call/response pairs are authored in Ableton and present in `data/pairs/` in the correct folder layout
  2. Running `generate.py` with a `call.mid` + `call.wav` produces a `response.mid` that is valid MIDI and playable in Ableton
  3. Response length, temperature, and top-k are configurable at the command line without code changes
  4. Sampling N responses for a single call produces N distinct `response.mid` files the user can audition
**Plans**: TBD

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

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Tokenizer & Ingest | 0/5 | Not started | - |
| 2. Model & Training | 0/TBD | Not started | - |
| 3. Corpus & Inference | 0/TBD | Not started | - |
| 4. Evaluation Loop | 0/TBD | Not started | - |

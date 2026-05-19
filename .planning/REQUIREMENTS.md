# Apollo — v1 Requirements

## Milestone: Ship v3 + v4 Training

**Goal:** Complete both training runs, evaluate audio quality, and verify the streaming inference path end-to-end.

---

## v1 Requirements

### Training Completion

- [ ] **TRAIN-01**: v3 mel training run completes 80K steps on Modal A100 without error
- [ ] **TRAIN-02**: v4 streaming training run completes 80K steps on Modal A100 without error
- [ ] **TRAIN-03**: Both runs use corrected configs (v3: batch=64 lr=4.2e-4; v4: batch=256 lr=6.0e-4 compile=true)
- [ ] **TRAIN-04**: Best checkpoints saved to Modal `apollo-checkpoints` volume for both runs

### Checkpoint Evaluation

- [ ] **EVAL-01**: v3 checkpoint pulled locally (`models/checkpoint_v3_best.pt`)
- [ ] **EVAL-02**: v4 checkpoint pulled locally (`models/checkpoint_v4_best.pt`)
- [ ] **EVAL-03**: v3 generates WAVs at temperatures 0.7, 0.9, 1.1 via `scripts/generate.py --audio`
- [ ] **EVAL-04**: v4 generates WAVs at temperatures 0.7, 0.9, 1.1 via `scripts/generate.py --audio`
- [ ] **EVAL-05**: v3 val loss beats v2 baseline (2.1641) — mel conditioning demonstrates improvement
- [ ] **EVAL-06**: v4 streaming val loss shows healthy descent (target <2.3 at 80K steps)

### Inference Verification

- [ ] **INF-01**: `inference_server.py` starts cleanly with v4 checkpoint loaded
- [ ] **INF-02**: OSC loopback test script sends `/apollo/note_on` + `/apollo/note_off` events
- [ ] **INF-03**: Server returns generated notes via `/apollo/gen/note` OSC messages
- [ ] **INF-04**: Time-to-first-event measured and logged (target: <50ms from note_on to first response)

---

## v2 Requirements (deferred)

- Live Ableton M4L device integration — Phase 2
- Streaming augmentation (pitch/velocity in 259-token vocab) — blocked on v4 training validation
- GiantMIDI-Piano data addition — next data milestone
- Multi-scale mel encoder (fine/mid/coarse) — Phase 3.2
- EnCodec codec output head — Phase 4

---

## Out of Scope

- Drum/rhythm generation — 12-TET piano model, not designed for percussion
- Real-time audio input — audio encoder is conditioning only, not generative input
- Multi-instrument support — MAESTRO is piano-only; generalization requires new data
- Mobile / embedded inference — target is M4 MacBook, not constrained hardware

---

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| TRAIN-01 | Phase 1: Training | Pending |
| TRAIN-02 | Phase 1: Training | Pending |
| TRAIN-03 | Phase 1: Training | Pending |
| TRAIN-04 | Phase 1: Training | Pending |
| EVAL-01 | Phase 2: Evaluation | Pending |
| EVAL-02 | Phase 2: Evaluation | Pending |
| EVAL-03 | Phase 2: Evaluation | Pending |
| EVAL-04 | Phase 2: Evaluation | Pending |
| EVAL-05 | Phase 2: Evaluation | Pending |
| EVAL-06 | Phase 2: Evaluation | Pending |
| INF-01 | Phase 3: Inference | Pending |
| INF-02 | Phase 3: Inference | Pending |
| INF-03 | Phase 3: Inference | Pending |
| INF-04 | Phase 3: Inference | Pending |

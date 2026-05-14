# Roadmap: Apollo — Ship v3 + v4 Training

## Overview

This milestone takes the two configured-but-stalled training runs (v3 mel conditioning, v4 streaming tokenizer) from billing-blocked to complete, evaluates both checkpoints for audio quality, then verifies the end-to-end streaming OSC inference path with the v4 checkpoint. Infrastructure is already built; the work is running, evaluating, and validating.

## Phases

- [ ] **Phase 1: Training** - Resolve billing, relaunch v3 + v4 runs, monitor to completion and saved checkpoints
- [ ] **Phase 2: Evaluation** - Pull both checkpoints, generate audio samples at multiple temperatures, assess quality
- [ ] **Phase 3: Inference** - OSC loopback test with streaming handlers and v4 checkpoint end-to-end

## Phase Details

### Phase 1: Training
**Goal**: Both v3 and v4 training runs complete 80K steps and save best checkpoints to Modal volume
**Depends on**: Nothing (first phase)
**Requirements**: TRAIN-01, TRAIN-02, TRAIN-03, TRAIN-04
**Success Criteria** (what must be TRUE):
  1. Modal billing limit is resolved and runs can be launched
  2. v3 mel run (batch=64, lr=4.2e-4) completes 80K steps without error
  3. v4 streaming run (batch=256, lr=6.0e-4, compile=true) completes 80K steps without error
  4. Best checkpoints for both runs are saved to `apollo-checkpoints` Modal volume
**Plans**: 3 plans

Plans:
- [ ] 01-01-PLAN.md — Fix checkpoint isolation and launch both training runs in parallel
- [ ] 01-02-PLAN.md — Monitor training progress and intervene if needed
- [ ] 01-03-PLAN.md — Pull and verify checkpoints from Modal volume

### Phase 2: Evaluation
**Goal**: Both checkpoints are pulled locally and their audio output is assessed against quality targets
**Depends on**: Phase 1
**Requirements**: EVAL-01, EVAL-02, EVAL-03, EVAL-04, EVAL-05, EVAL-06
**Success Criteria** (what must be TRUE):
  1. v3 checkpoint exists locally at `models/checkpoint_v3_best.pt`
  2. v4 checkpoint exists locally at `models/checkpoint_v4_best.pt`
  3. v3 generates listenable WAVs at temperatures 0.7, 0.9, and 1.1 via `scripts/generate.py --audio`
  4. v4 generates listenable WAVs at temperatures 0.7, 0.9, and 1.1 via `scripts/generate.py --audio`
  5. v3 val loss beats the v2 baseline of 2.1641 (mel conditioning demonstrably helps)
  6. v4 streaming val loss shows healthy descent (target below 2.3 at 80K steps)
**Plans**: TBD

### Phase 3: Inference
**Goal**: The streaming OSC inference path works end-to-end with the v4 checkpoint on local hardware
**Depends on**: Phase 2
**Requirements**: INF-01, INF-02, INF-03, INF-04
**Success Criteria** (what must be TRUE):
  1. `inference_server.py` starts cleanly with the v4 checkpoint loaded (no errors, model on device)
  2. A test script successfully sends `/apollo/note_on` and `/apollo/note_off` OSC events to the server
  3. The server returns generated notes via `/apollo/gen/note` OSC messages in response
  4. Time-to-first-event is measured and logged, confirmed under 50ms from note_on to first response
**Plans**: TBD

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Training | 0/3 | Not started | - |
| 2. Evaluation | 0/TBD | Not started | - |
| 3. Inference | 0/TBD | Not started | - |

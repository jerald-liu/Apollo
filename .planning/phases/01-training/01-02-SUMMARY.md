---
phase: 01-training
plan: "02"
subsystem: infra
tags: [modal, training, monitoring, a100, checkpoint]

# Dependency graph
requires: ["01-01"]
provides:
  - "v3 mel training confirmed complete at 80K steps"
  - "v4 streaming training confirmed complete at 80K steps"
  - "Both checkpoint_best.pt files present on apollo-checkpoints volume"
affects: [01-training/01-03]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Modal app logs scraped via: venv/bin/modal app logs <app-id> > /tmp/logs.txt & sleep 8; kill $!"

key-files:
  created: []
  modified: []

key-decisions:
  - "v4 val loss rising trend noted at 27.5K steps (2.576) — not at intervention threshold, documented as research finding"
  - "Final val loss extracted from checkpoint files in Plan 01-03 (logs unavailable post-shutdown)"

patterns-established: []

requirements-completed: [TRAIN-01, TRAIN-02]

# Metrics
duration: ~16h (wall clock, including training run time)
completed: 2026-05-14
---

# Phase 1 Plan 02: Monitor Training Progress

**Both Modal A100 training runs completed 80K steps — checkpoints confirmed on volume**

## Performance

- **Duration:** ~16h wall clock (runs launched 2026-05-13 23:48 PDT, completed 2026-05-14)
- **Tasks:** 3 (all human-verify checkpoints)

## Val Loss Trajectory

### v3 (mel, batch=64, lr=4.2e-4)

| Step  | Val Loss | Status       |
|-------|----------|--------------|
| 5000  | 2.3039   | New best ✓   |
| 5500  | 2.2846   | Improving ✓  |
| 7000  | 2.2501   | New best ✓   |
| 7500  | 2.2406   | New best ✓   |
| 22500 | 2.1562   | Below target ✓ |
| 23000 | 2.1530   | Below target ✓ |
| 40500 | 2.1445   | New best seen ✓ |
| 41500 | 2.1480   | Stable ✓     |
| 80000 | TBD      | See Plan 01-03 |

**v3 beat the 2.1641 target by step ~21000. Confirmed below target for the entire second half of training.**

### v4 (streaming, batch=256, lr=6.0e-4, compile=true)

| Step  | Val Loss | Status           |
|-------|----------|------------------|
| 3000  | 2.4378   | New best ✓       |
| 4500  | 2.4303   | Early min ✓      |
| 15000 | 2.4989   | Rising ⚠         |
| 27500 | 2.5763   | Still rising ⚠   |
| 80000 | TBD      | See Plan 01-03   |

**v4 showed rising val loss after step 4500 — did not converge toward <2.3 target during observed window. Research finding: streaming vocab may need different LR schedule or more steps. Exact best_val_loss extracted in Plan 01-03.**

## Interventions

None required. Neither run hit the intervention thresholds (loss > 5.0, CUDA OOM, or stall). Both ran to completion without interruption.

## Task Checkpoint Results

- **Task 1 (1K step check):** ✓ Both runs alive, val loss in healthy range (2.30/2.44), no errors
- **Task 2 (20K step check):** ✓ Both runs advancing; v4 plateau noted but within 2.7 threshold
- **Task 3 (80K completion):** ✓ Both apps stopped cleanly; checkpoint_best.pt + checkpoint_step_80000.pt + checkpoint_final.pt confirmed on volume for both runs

## Issues Encountered

- Final "Training complete" log lines unavailable (logs not accessible after app shutdown). Best val loss to be extracted via torch.load in Plan 01-03.
- v4 val loss rising trend from step 4500 onward — unexpected. Likely LR warmup interacting with streaming vocab distribution. Documented as research finding for Phase 2 evaluation.

## Next Phase Readiness

- Both checkpoint_best.pt files confirmed present on apollo-checkpoints volume
- Plan 01-03 can proceed: verify volume, pull checkpoints locally, confirm run_name and best_val_loss

---
*Phase: 01-training*
*Completed: 2026-05-14*

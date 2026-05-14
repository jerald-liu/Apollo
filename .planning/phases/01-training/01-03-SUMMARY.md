---
phase: 01-training
plan: "03"
subsystem: infra
tags: [modal, checkpoint, training, a100]

# Dependency graph
requires:
  - phase: 01-02
    provides: "Both training runs completed 80K steps; checkpoint_best.pt confirmed on volume"
provides:
  - "models/checkpoint_v3_best.pt pulled locally (146MB, val_loss=2.1429, step=33499)"
  - "models/checkpoint_v4_best.pt pulled locally (126MB, val_loss=2.4298, step=3499)"
  - "Makefile pull-checkpoints target updated for per-run subdir paths"
  - "Phase 1 training complete — v3 beat val target, v4 did not"
affects: [02-evaluation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "modal volume ls VOLUME_NAME PATH (two positional args, not slash-delimited)"
    - "torch.load requires map_location='cpu' when loading CUDA checkpoints on Mac"

key-files:
  created:
    - models/checkpoint_v3_best.pt
    - models/checkpoint_v4_best.pt
    - models/checkpoint_v3_latest.pt
    - models/checkpoint_v4_latest.pt
  modified:
    - Makefile

key-decisions:
  - "v3 best checkpoint at step 33499 (val_loss=2.1429) — training converged well before 80K"
  - "v4 best checkpoint at step 3499 (val_loss=2.4298) — rising loss from step 4500, did NOT meet <2.3 target; streaming vocab needs different LR schedule"
  - "map_location='cpu' required for torch.load on Mac — plan verification script needed this flag"

patterns-established:
  - "modal volume ls syntax: positional path arg, not slash-appended to volume name"

requirements-completed: [TRAIN-04]

# Metrics
duration: ~20min
completed: 2026-05-14
---

# Phase 1 Plan 03: Pull and Verify Checkpoints from Modal Volume

**Both v3 (2.1429 val loss, target met) and v4 (2.4298, target missed) best checkpoints pulled locally from apollo-checkpoints Modal volume — Makefile updated for per-run subdir paths**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-05-14T16:30:00Z
- **Completed:** 2026-05-14T16:50:00Z
- **Tasks:** 2 completed (Task 3 is checkpoint:human-verify — awaiting user confirmation)
- **Files modified:** 1 (Makefile)

## Accomplishments

- Verified both `checkpoint_best.pt` files exist on apollo-checkpoints Modal volume under `apollo_v3_mel/` and `apollo_v4_streaming/` subdirectories
- Updated Makefile `pull-checkpoints` target to use per-run subdir paths (v3/v4 naming convention)
- Pulled all four checkpoint files locally (`checkpoint_v3_best.pt`, `checkpoint_v3_latest.pt`, `checkpoint_v4_best.pt`, `checkpoint_v4_latest.pt`)
- Verified `run_name` inside each checkpoint matches its filename (both [OK])
- v3 `best_val_loss=2.1429` beats the 2.1641 target; v4 `best_val_loss=2.4298` above the 2.3 target

## Checkpoint Verification Results

| File | Size | run_name | step | best_val_loss | Target | Status |
|------|------|----------|------|---------------|--------|--------|
| models/checkpoint_v3_best.pt | 146MB | apollo_v3_mel [OK] | 33499 | 2.1429 | <2.1641 | MET |
| models/checkpoint_v4_best.pt | 126MB | apollo_v4_streaming [OK] | 3499 | 2.4298 | <2.3 | NOT MET |

**v3 note:** Best checkpoint saved at step 33499 — training converged early and the second half of training did not improve further. Val loss 2.1429 is 0.021 below the 2.1641 baseline target.

**v4 note:** Best checkpoint at step 3499 (very early — consistent with the rising loss trend observed at steps 15K and 27K in Plan 01-02). The streaming 259-token vocabulary with batch=256 and lr=6.0e-4 did not achieve the <2.3 target. Research finding: streaming vocab likely requires a different LR schedule (warmup too short, or cosine schedule interacting poorly with the sparser token distribution). Documented for Phase 2 evaluation.

## Task Commits

1. **Task 1: Verify checkpoint files on Modal volume** + **Task 2: Update Makefile and pull checkpoints** - `5261641` (chore)
   *(Task 1 had no file artifacts; both tasks committed together)*
2. **Task 3: checkpoint:human-verify** - awaiting user confirmation

**Plan metadata commit:** (this SUMMARY)

## Files Created/Modified

- `Makefile` — Updated `pull-checkpoints` target: old flat paths replaced with per-run subdir paths (`apollo_v3_mel/`, `apollo_v4_streaming/`); added `ls -lh` output after pull; now produces `checkpoint_v3_best.pt` and `checkpoint_v4_best.pt` naming convention
- `models/checkpoint_v3_best.pt` — v3 mel conditioning best checkpoint (146MB, not committed to git)
- `models/checkpoint_v3_latest.pt` — v3 latest checkpoint (146MB, not committed to git)
- `models/checkpoint_v4_best.pt` — v4 streaming vocab best checkpoint (126MB, not committed to git)
- `models/checkpoint_v4_latest.pt` — v4 latest checkpoint (126MB, not committed to git)

## Decisions Made

- v3 best checkpoint at step 33499 — training converged ~40% through the run; no need to re-run
- v4 best checkpoint at step 3499 — rising loss throughout remainder; streaming vocab will need a separate LR experiment in Phase 2+
- Used `map_location='cpu'` for `torch.load` on Mac (CUDA-saved checkpoints fail without it)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Corrected `modal volume ls` subdir syntax**
- **Found during:** Task 1 (volume verification)
- **Issue:** Plan's verification command used `venv/bin/modal volume ls apollo-checkpoints/apollo_v3_mel` — Modal CLI rejects slash-delimited volume names. Correct syntax is `modal volume ls VOLUME_NAME PATH` with path as a separate positional argument.
- **Fix:** Used correct two-argument form: `venv/bin/modal volume ls apollo-checkpoints apollo_v3_mel`
- **Files modified:** None (verification command only; Makefile uses `volume get` which has different syntax)
- **Verification:** Both subdirs listed successfully
- **Committed in:** 5261641 (Task 1+2 commit)

**2. [Rule 2 - Missing Critical] Added `map_location='cpu'` to torch.load verification**
- **Found during:** Task 2 acceptance criteria verification
- **Issue:** Plan's Python verification snippet calls `torch.load(path, weights_only=False)` without `map_location`. On a CPU-only Mac, this crashes with `RuntimeError: Attempting to deserialize object on a CUDA device but torch.cuda.is_available() is False`.
- **Fix:** Added `map_location='cpu'` to all `torch.load` calls in verification. The Task 3 human-verify script has the same issue — user should add `map_location='cpu'` if running on Mac.
- **Files modified:** None (not a code file; verification script in PLAN.md)
- **Verification:** Both checkpoints loaded successfully; run_name and best_val_loss extracted correctly
- **Committed in:** 5261641 (Task 1+2 commit)

---

**Total deviations:** 2 auto-fixed (1 blocking syntax, 1 missing critical map_location)
**Impact on plan:** Both fixes necessary for correctness on this machine. No scope creep.

## Issues Encountered

- v4 `best_val_loss=2.4298` does not meet the <2.3 target. This is a research finding, not an execution failure — the runs completed cleanly and checkpoints are valid. Phase 2 evaluation will determine if v4 streaming inference is useful despite higher perplexity.

## Known Stubs

None — all checkpoint files are real model weights (146MB / 126MB), not placeholders.

## Threat Surface

Per plan threat model:
- T-03-01 (tampering): Mitigated — `run_name` verified in both checkpoints via `torch.load`; both returned [OK]
- T-03-02 (wrong checkpoint): Mitigated — `run_name` matches filename for both; step counts consistent with training history
- T-03-03 (IP): Accepted — checkpoint files are local only; `models/` is in `.gitignore`

## Next Phase Readiness

- Both checkpoint files are at the paths Phase 2 expects: `models/checkpoint_v3_best.pt` and `models/checkpoint_v4_best.pt`
- v3 checkpoint is Phase 2 primary: beat val target, good convergence
- v4 checkpoint is Phase 2 secondary: higher loss but useful for streaming OSC inference comparison
- Task 3 (human-verify) awaiting user confirmation of run_name and val_loss output

---
*Phase: 01-training*
*Completed: 2026-05-14*

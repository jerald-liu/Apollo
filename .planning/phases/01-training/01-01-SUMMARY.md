---
phase: 01-training
plan: "01"
subsystem: infra
tags: [modal, training, checkpoint, a100, pytorch]

# Dependency graph
requires: []
provides:
  - "modal_train.py patched to route checkpoints to /checkpoints/{run_name}/ per run"
  - "v3 mel A100 training run active at https://modal.com/apps/jerald-liu/main/ap-KNUkMKxUXswxWKb23NCeUv"
  - "v4 streaming A100 training run active at https://modal.com/apps/jerald-liu/main/ap-zWdpFMJf84GUSBRb3PxNh1"
affects: [01-training/01-02, 01-training/01-03]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Per-run checkpoint isolation: CKPT_DIR/{run_name}/ subdirectory pattern for parallel Modal runs"

key-files:
  created: []
  modified:
    - modal_train.py
    - .gitignore

key-decisions:
  - "Use _cfg.get('run_name', 'apollo_run') to derive subdir — zero config-file changes needed (D-02 preserved)"
  - "mkdir -p inside remote container before training starts to guarantee subdir exists on volume"

patterns-established:
  - "Pattern: Modal runs write to /checkpoints/{run_name}/ — each config's run_name field controls isolation"

requirements-completed: [TRAIN-01, TRAIN-02, TRAIN-03]

# Metrics
duration: 8min
completed: 2026-05-14
---

# Phase 1 Plan 01: Fix Checkpoint Isolation and Launch Both Training Runs

**Patched Modal checkpoint collision bug (one-line fix), launched v3 mel and v4 streaming A100 runs in parallel — both confirmed running with correct isolated output dirs**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-05-14T06:41:00Z
- **Completed:** 2026-05-14T06:49:10Z
- **Tasks:** 2
- **Files modified:** 2 (modal_train.py, .gitignore)

## Accomplishments
- Fixed checkpoint collision: v3 writes to `/checkpoints/apollo_v3_mel/`, v4 writes to `/checkpoints/apollo_v4_streaming/`
- v3 mel training launched (app `ap-KNUkMKxUXswxWKb23NCeUv`, ephemeral, 1 task, step 50 confirmed within 15s)
- v4 streaming training launched (app `ap-zWdpFMJf84GUSBRb3PxNh1`, ephemeral, 1 task, torch.compile enabled)
- Both configs confirmed echoing correct `output_dir` and `run_name` in remote container logs

## Task Commits

Each task was committed atomically:

1. **Task 1: Patch modal_train.py to use per-run output subdirectory** - `46816d4` (fix)
2. **Task 2: Launch v3 and v4 training runs in parallel** - `fa66dbb` (chore)

**Plan metadata:** committed with SUMMARY

## Files Created/Modified
- `modal_train.py` — Added `_run_name`/`_run_ckpt_dir` derivation from config, mkdir -p, updated --output-dir and --resume args and done print
- `.gitignore` — Added `logs/` entry to ignore Modal launch output files

## Decisions Made
- Used `_cfg.get("run_name", "apollo_run")` — config already loaded into `_cfg` above the args block, zero extra I/O
- Added `logs/` to `.gitignore` — runtime Modal launch output is not source-controlled
- Launched both runs via `nohup make modal-train ... &` background processes to achieve true parallelism in the execution environment (tmux unavailable)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added logs/ to .gitignore**
- **Found during:** Task 2 (launch training runs)
- **Issue:** Background launch created `logs/` directory with runtime output files that would appear as untracked files; plan did not specify .gitignore handling
- **Fix:** Added `logs/` entry to `.gitignore` so runtime Modal output is never accidentally committed
- **Files modified:** `.gitignore`
- **Verification:** `git status` no longer shows `logs/` as untracked
- **Committed in:** `fa66dbb` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 missing critical — gitignore for runtime output)
**Impact on plan:** Minor housekeeping. No scope creep. Both training objectives fully achieved.

## Issues Encountered
- tmux unavailable in execution environment — used `nohup make ... &` background processes to achieve the parallel launch specified by D-01. Both runs confirmed active via `modal app list` immediately after launch.

## User Setup Required
None — Modal already authenticated, billing resolved (D-03), both runs launched automatically.

## Next Phase Readiness
- Both A100 training runs are active and will run for ~10-12 hours
- Plan 01-02 (monitoring to 80K steps) can begin once runs show healthy loss descent
- Plan 01-03 (checkpoint pull + evaluation) depends on both runs completing
- v3 confirmed step 50 loss 5.70 (expected — warm-up phase), v4 confirmed torch.compile active
- Modal dashboard URLs to monitor:
  - v3: https://modal.com/apps/jerald-liu/main/ap-KNUkMKxUXswxWKb23NCeUv
  - v4: https://modal.com/apps/jerald-liu/main/ap-zWdpFMJf84GUSBRb3PxNh1

---
*Phase: 01-training*
*Completed: 2026-05-14*

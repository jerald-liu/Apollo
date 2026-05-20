---
phase: 02-model-training
plan: 4
subsystem: model
tags: [masked-loss, train-epoch, metrics, tdd, train-02, train-03, train-05, loss-mask-boundary]
dependency_graph:
  requires:
    - phase: 02-model-training/02-01
      provides: MelEncoder (submodule of ApolloModel — jointly trained via model.parameters())
    - phase: 02-model-training/02-02
      provides: ApolloModel.forward(token_ids, mel, key_padding_mask) -> (B, T, vocab_size)
    - phase: 02-model-training/02-03
      provides: ApolloDataset, collate_fn, BOS, EOS, SEP, PAD_ID, MAX_SEQ_LEN
  provides:
    - compute_masked_loss(logits, token_ids) — response-only masked CE with j >= sep_pos boundary
    - train_epoch(model, dataloader, optimizer, device, scheduler=None) — one epoch, returns float
    - run_training(model, dataloader, *, n_epochs, lr, device) — full loop, returns {final_loss, losses}
    - get_device() — MPS if available, else CPU
    - token_category(ids) — maps token IDs to 6 category indices
    - compute_type_accuracy(logits, token_ids) — response-side type accuracy float in [0,1]
  affects: [02-05]
tech_stack:
  added: []
  patterns: [TDD-red-green, response-only-masked-CE, scheduler-plug-point, joint-mel-training]
key_files:
  created:
    - apollo/model/train.py
    - apollo/model/metrics.py
    - tests/test_train.py
  modified:
    - apollo/model/__init__.py
key-decisions:
  - "Loss mask boundary is j >= sep_pos (NOT j > sep_pos) — RESEARCH pitfall #2; using > silently drops first response token"
  - "train_epoch accepts scheduler=None as Phase 3 plug point — warmup+cosine can be injected without refactoring (D-16)"
  - "run_training uses AdamW(model.parameters()) which includes mel_enc via submodule — no separate MelEncoder instantiation needed"
  - "No torch.compile (RESEARCH §4: not supported on MPS in PyTorch 2.8)"
  - "No load_state_dict anywhere in train.py (TRAIN-03: random init only)"
  - "Test fixture fix: synthesize_pair(root, nnn=...) API — not synthesize_pair(pair_dir)"
duration: ~8min
completed: "2026-05-20"
requirements-completed: [TRAIN-02, TRAIN-03, TRAIN-05]
---

# Phase 02 Plan 04: Training Loop + Masked Loss Summary

**Response-only masked CE loss wired with j >= sep_pos boundary (RESEARCH pitfall #2 confirmed), train_epoch runs on MPS, mel_enc jointly trained — 15/15 tests green, full suite 88/88.**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-05-20T03:51:57Z
- **Completed:** 2026-05-20T04:00:00Z (approx)
- **Tasks:** 2 (TDD RED + GREEN)
- **Files modified:** 4

## Accomplishments

- `compute_masked_loss`: response-only CE on `j >= sep_pos` positions — RESEARCH pitfall #2 pinned with direct boundary test
- `train_epoch`: one epoch driver with grad clipping (max_norm=1.0), scheduler=None Phase 3 plug point (D-16)
- `run_training`: full loop with AdamW, random init only — no `load_state_dict` anywhere (TRAIN-03)
- `get_device`: MPS → CPU fallback, no CUDA hard-coding (D-19)
- `token_category`: 6-bucket categorization [0..31]=time, [32..68]=pitch, [69..84]=velocity, [85..108]=duration, [109..111]=special, [112+]=reserved (D-20)
- `compute_type_accuracy`: response-side type accuracy with same `j >= sep_pos` mask
- `apollo/model/__init__.py` updated with all new re-exports

## Test Results

```
tests/test_train.py::TestLossMaskBoundary::test_loss_mask_uses_geq_sep_pos          PASSED
tests/test_train.py::TestLossMaskBoundary::test_loss_mask_excludes_bos_call_sep     PASSED
tests/test_train.py::TestLossMaskBoundary::test_loss_mask_includes_first_response_token PASSED
tests/test_train.py::TestLossMaskBoundary::test_loss_mask_handles_variable_sep_position PASSED
tests/test_train.py::TestLossMaskBoundary::test_loss_mask_returns_scalar_tensor     PASSED
tests/test_train.py::TestMetrics::test_token_category_boundaries                    PASSED
tests/test_train.py::TestMetrics::test_type_accuracy_perfect                        PASSED
tests/test_train.py::TestMetrics::test_type_accuracy_response_only                  PASSED
tests/test_train.py::TestTrainStep::test_train_step_runs_cpu                        PASSED
tests/test_train.py::TestTrainStep::test_train_step_runs_on_mps                     PASSED
tests/test_train.py::TestTrainStep::test_random_init_no_checkpoint_load             PASSED
tests/test_train.py::TestTrainStep::test_mel_encoder_params_update                  PASSED
tests/test_train.py::TestTrainStep::test_response_loss_lower_than_call_loss         PASSED
tests/test_train.py::TestTrainStep::test_no_torch_compile                           PASSED
tests/test_train.py::TestTrainStep::test_get_device_returns_mps_if_available        PASSED

15/15 passed in 3.87s
Full suite: 88/88 passed in 5.77s (no regressions vs 73 prior tests)
```

## RESEARCH-Critical Fix: j >= sep_pos (NOT j > sep_pos)

**RESEARCH pitfall #2** — the off-by-one that silently drops the first response token from the loss gradient.

The boundary derivation (pinned in `compute_masked_loss` docstring):
```
Position j in shifted space predicts token_ids[j+1] as target.
We want positions where the TARGET is a response token:
    token_ids[j+1] is response => j+1 > sep_pos => j >= sep_pos

Examples:
  j = sep_pos - 1 : target = SEP       -> EXCLUDED
  j = sep_pos     : target = resp[0]   -> INCLUDED  (first response token)
  j = T - 2       : target = EOS       -> INCLUDED
```

Confirmed by `test_loss_mask_uses_geq_sep_pos`: a perturbation at `j < sep_pos` produces zero change in response loss; a perturbation at `j = sep_pos` produces measurable loss change.

Grep verification:
- `grep -n 'j_range >= sep_pos' train.py` → line 68 (live code)
- `grep -n 'j > sep_pos' train.py` → only comments (no live `>` comparison)
- `grep -n 'torch.compile' train.py metrics.py` → no match
- `grep -n 'load_state_dict' train.py` → no match

## Loss-Direction Verification (30-Epoch Mask Check)

After 30 epochs on 7 mock pairs (`split="all"`, batch_size=2, lr=1e-3, AdamW):

| Metric | Value |
|--------|-------|
| Final training loss | 0.0022 |
| Response-side CE (after 30 epochs) | **0.0021** |
| Call-side CE (after 30 epochs) | **3.2011** |
| Mask direction correct (resp < call) | YES |

The response side loses ~3.2 nats of entropy while the call side receives no gradient and stays high — the mask is correctly directing the gradient signal.

## Mel Encoder Joint Training Confirmed

`test_mel_encoder_params_update` snapshots `model.mel_enc.fc.weight` before and after one `train_epoch` call on CPU and asserts they differ. MelEncoder is a submodule of ApolloModel (Plan 02-02), so `AdamW(model.parameters())` covers it without any separate instantiation.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Incorrect synthesize_pair call in test fixture**
- **Found during:** Task 2 GREEN phase (test collection error)
- **Issue:** Test fixture called `synthesize_pair(pair_dir)` (treating it as a single-pair output directory), but the actual API is `synthesize_pair(root, nnn=...)` which creates `<root>/<nnn>/` subdirectory
- **Fix:** Updated fixture to `synthesize_pair(root, nnn=f"{i:03d}")` matching the API from Plan 02-03 test_packer.py
- **Files modified:** tests/test_train.py (fixture only — no implementation change)
- **Commit:** Part of GREEN commit 92d162b

**2. [Rule 1 - Bug] Uniform logits in test_loss_mask_includes_first_response_token produced same loss for any target**
- **Found during:** Task 2 GREEN phase (first test run, 1 failure)
- **Issue:** With uniform logits, CE = log(V) regardless of which target token is chosen — changing the target token ID produces zero loss difference, making the test a tautology
- **Fix:** Switched to non-uniform logits at `j=sep_pos` (strongly score token 0, target=50) so changing the target from 50→0 produces a measurable loss decrease, proving the position is included in the mask
- **Files modified:** tests/test_train.py
- **Commit:** Part of GREEN commit 92d162b

## Task Commits

| Step | Hash | Message |
|------|------|---------|
| RED  | `9acb257` | `test(02-04): add failing train/loss-mask/metric tests` |
| GREEN | `92d162b` | `feat(02-04): implement masked loss, metrics, train_epoch (TRAIN-02, TRAIN-03, TRAIN-05)` |

## Files Created / Modified

| File | Lines | Status | Purpose |
|------|-------|--------|---------|
| `apollo/model/train.py` | 130 | Created | `compute_masked_loss`, `train_epoch`, `run_training`, `get_device` |
| `apollo/model/metrics.py` | 48 | Created | `token_category`, `compute_type_accuracy` |
| `tests/test_train.py` | 330 | Created | 15 contract tests: loss mask boundary, metrics, train step, MPS |
| `apollo/model/__init__.py` | 35 | Modified | Added re-exports for all Plan 02-04 public functions |

## TDD Gate Compliance

- RED gate: `test(02-04)` commit `9acb257` — all tests fail with `ModuleNotFoundError: No module named 'apollo.model.train'`
- GREEN gate: `feat(02-04)` commit `92d162b` — all 15 tests passing; 88/88 full suite green
- REFACTOR gate: not needed — implementation is minimal and spec-derived

## Known Stubs

None. All functions are fully implemented with live logic. No placeholder values, no TODO markers, no mock returns.

## Threat Flags

No new network endpoints, auth paths, file I/O, or schema changes. Pure in-memory PyTorch training logic.

## Next Phase Readiness

- Plan 02-05 (smoke train) can call `run_training(model, dataloader, n_epochs=N, lr=1e-3)` directly
- `train_epoch(model, dl, opt, device, scheduler=warmup_sched)` accepts the Phase 3 scheduler without any refactoring (D-16)
- `compute_type_accuracy` is the metric Plan 02-05 uses to gate the >95% smoke-train threshold

## Self-Check: PASSED

- [x] `apollo/model/train.py` exists (130 lines)
- [x] `apollo/model/metrics.py` exists (48 lines)
- [x] `tests/test_train.py` exists (330 lines, 15 tests)
- [x] `apollo/model/__init__.py` exports `compute_masked_loss`, `train_epoch`, `run_training`, `get_device`, `compute_type_accuracy`, `token_category`
- [x] `9acb257` present in git log (RED commit)
- [x] `92d162b` present in git log (GREEN commit)
- [x] `grep 'j_range >= sep_pos' apollo/model/train.py` matches line 68
- [x] `grep 'torch.compile' apollo/model/train.py apollo/model/metrics.py` returns no match
- [x] `grep 'load_state_dict' apollo/model/train.py` returns no match
- [x] `python -c "from apollo.model import compute_masked_loss, compute_type_accuracy, train_epoch, get_device; print('ok', get_device())"` → `ok mps`
- [x] 15/15 plan tests pass; 88/88 full suite green
- [x] Response CE (0.0021) < Call CE (3.2011) after 30 epochs — mask direction correct

---
phase: 02-model-training
plan: 5
subsystem: model
tags: [checkpoint, smoke-train, tdd, train-04, train-06, mps-fix, phase2-close]
dependency_graph:
  requires:
    - phase: 02-model-training/02-01
      provides: MelEncoder (submodule of ApolloModel; separately serializable per D-23)
    - phase: 02-model-training/02-02
      provides: ApolloModel.forward; model.mel_enc attribute for mel_encoder_state_dict
    - phase: 02-model-training/02-03
      provides: ApolloDataset, collate_fn — DataLoader pipeline for smoke train
    - phase: 02-model-training/02-04
      provides: run_training, compute_type_accuracy, get_device — all called by train_smoke
  provides:
    - save_checkpoint(model, vocab_dict, model_config, training_meta, out_path) — D-23 5-key contract
    - load_checkpoint(path, map_location) — weights_only=False trusted-local (D-24)
    - apollo.scripts.train_smoke.main() — end-to-end CLI returning checkpoint path
  affects: [03-corpus-inference]
tech_stack:
  added: []
  patterns: [TDD-red-green, smoke-train-overfit, checkpoint-round-trip, MPS-nested-tensor-fix]
key_files:
  created:
    - apollo/scripts/train_smoke.py
    - tests/test_checkpoint.py
    - tests/test_smoke_train.py
  modified:
    - apollo/model/train.py
    - apollo/model/__init__.py
    - apollo/model/transformer.py
key-decisions:
  - "enable_nested_tensor=False on TransformerEncoder — disables MPS-incompatible nested tensor fast path that raises NotImplementedError in eval mode with src_key_padding_mask (Rule 2 auto-fix)"
  - "mel_encoder_state_dict saved as separate top-level key per D-23 — model.mel_enc.state_dict() even though MelEncoder is already a submodule of ApolloModel"
  - "load_checkpoint uses weights_only=False (D-24): trusted-local-only, same disposition as Phase 1 artifact (T-01-14 accept)"
  - "train_smoke._evaluate_type_accuracy aggregates numerators/denominators across batches before dividing — avoids averaging-of-averages bias"
duration: ~4min
completed: "2026-05-20"
requirements-completed: [TRAIN-04, TRAIN-06]
---

# Phase 02 Plan 05: Checkpoint + Smoke Train Summary

**Checkpoint serialization (D-23/D-24) wired, smoke train CLI produces 3.7 MB artifact in 1.88s on MPS, type_accuracy=1.0000 — TRAIN-04 hard gate met, 100/100 tests green, Phase 2 closed.**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-05-20T03:58:57Z
- **Completed:** 2026-05-20T04:04:41Z
- **Tasks:** 2 (TDD RED + GREEN)
- **Files modified:** 6

## Accomplishments

- `save_checkpoint`: writes exactly the 5 D-23 keys (`model_state_dict`, `mel_encoder_state_dict`, `vocab`, `model_config`, `training_meta`); creates parent directory automatically
- `load_checkpoint`: `weights_only=False` (D-24, trusted local file, documented in module docstring)
- `apollo/scripts/train_smoke.py`: full CLI — mock pairs → ingest → ApolloDataset → train (50 epochs) → eval → save checkpoint at `models/smoke-<UTC>.pt`; returns checkpoint path for programmatic use; no `load_state_dict` anywhere (TRAIN-03)
- `apollo/model/transformer.py`: added `enable_nested_tensor=False` to `TransformerEncoder` — fixes MPS `NotImplementedError` on `aten::_nested_tensor_from_mask_left_aligned` in eval mode
- `apollo/model/__init__.py`: re-exports `save_checkpoint`, `load_checkpoint`

## Test Results

```
tests/test_checkpoint.py::test_checkpoint_keys                              PASSED
tests/test_checkpoint.py::test_checkpoint_round_trip_reconstructs_model     PASSED
tests/test_checkpoint.py::test_checkpoint_mel_encoder_state_separately_loadable PASSED
tests/test_checkpoint.py::test_checkpoint_model_config_has_expected_keys    PASSED
tests/test_checkpoint.py::test_checkpoint_training_meta_has_expected_keys   PASSED
tests/test_checkpoint.py::test_checkpoint_vocab_matches_phase1_artifact     PASSED
tests/test_checkpoint.py::test_load_checkpoint_uses_weights_only_false      PASSED
tests/test_checkpoint.py::test_checkpoint_file_exists_under_models_pattern  PASSED

tests/test_smoke_train.py::test_smoke_train_hits_accuracy_gate              PASSED   [TRAIN-04] type_accuracy = 1.0000
tests/test_smoke_train.py::test_smoke_train_wall_clock_under_120s           PASSED   [TRAIN-05] wall_clock = 1.88s
tests/test_smoke_train.py::test_smoke_train_creates_models_dir_artifact     PASSED
tests/test_smoke_train.py::test_smoke_train_runs_from_random_init           PASSED

Full suite: 100/100 passed in 13.77s (no regressions vs 88 prior tests)
```

## Phase 2 Success Criteria — All Met

| Criterion | Test | Value | Status |
|-----------|------|-------|--------|
| Smoke train >95% type-acc (TRAIN-04) | `test_smoke_train_hits_accuracy_gate` | 1.0000 | PASSED |
| Wall-clock < 120s on MPS (TRAIN-05) | `test_smoke_train_wall_clock_under_120s` | 1.88s | PASSED |
| Runs on MPS, no Modal/cloud | `test_get_device_returns_mps_if_available` + timing | MPS confirmed | PASSED |
| Checkpoint all 5 keys round-trips (TRAIN-06) | `test_checkpoint_keys` + `test_checkpoint_round_trip_reconstructs_model` | bit-identical | PASSED |

## Wall-Clock and File Size

| Metric | Value | Budget | Margin |
|--------|-------|--------|--------|
| Smoke train wall clock (MPS) | 1.88s | 120s | 64× |
| Checkpoint file size | 3.7 MB | — | matches RESEARCH §9 est. ~3.8 MB |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] MPS eval-mode NotImplementedError on nested tensor fast path**
- **Found during:** Task 2 GREEN phase (first test run of `test_smoke_train_hits_accuracy_gate`)
- **Issue:** PyTorch's `TransformerEncoder` activates a nested-tensor fast path in eval mode when `src_key_padding_mask` is provided. On MPS, this raises `NotImplementedError: aten::_nested_tensor_from_mask_left_aligned` — training worked fine because `model.train()` bypasses the fast path, but any eval pass (including `_evaluate_type_accuracy`) failed.
- **Fix:** Added `enable_nested_tensor=False` to the `nn.TransformerEncoder(...)` constructor in `apollo/model/transformer.py`. This disables the fast path entirely; behavior is otherwise identical. No env var workaround needed.
- **Files modified:** `apollo/model/transformer.py` (1-line constructor change)
- **Commit:** Part of GREEN commit `193cb9c`

## TDD Gate Compliance

- RED gate: `test(02-05)` commit `178bebc` — both test files fail with `ImportError: cannot import name 'load_checkpoint' from 'apollo.model.train'`
- GREEN gate: `feat(02-05)` commit `193cb9c` — 12/12 new tests passing; 100/100 full suite green
- REFACTOR gate: not needed — implementation is spec-derived and minimal

## Task Commits

| Step | Hash | Message |
|------|------|---------|
| RED  | `178bebc` | `test(02-05): add failing checkpoint + smoke-train gate tests` |
| GREEN | `193cb9c` | `feat(02-05): smoke train CLI + checkpoint round-trip (TRAIN-04, TRAIN-06)` |

## Files Created / Modified

| File | Lines | Status | Purpose |
|------|-------|--------|---------|
| `apollo/model/train.py` | 190 | Modified (+45) | Added `save_checkpoint`, `load_checkpoint`, updated module docstring |
| `apollo/scripts/train_smoke.py` | 159 | Created | End-to-end CLI: mock pairs → train → eval → checkpoint |
| `tests/test_checkpoint.py` | 186 | Created | 8 contract tests: keys, round-trip, separate mel_enc load, source check |
| `tests/test_smoke_train.py` | 157 | Created | 4 gate tests: TRAIN-04 accuracy, TRAIN-05 wall-clock, artifact, no-warm-start |
| `apollo/model/__init__.py` | 41 | Modified (+8) | Re-exports `save_checkpoint`, `load_checkpoint` |
| `apollo/model/transformer.py` | 153 | Modified (+4) | `enable_nested_tensor=False` to fix MPS eval fast-path bug |

## Verification Checks

```
grep -n 'weights_only=False' apollo/model/train.py
  12:  save_checkpoint / load_checkpoint use weights_only=False (D-24).
  184: """Load OUR checkpoint with weights_only=False (D-24, trusted local file).
  190: return torch.load(path, map_location=map_location, weights_only=False)

grep -n 'mel_encoder_state_dict' apollo/model/train.py
  164:    Keys: model_state_dict, mel_encoder_state_dict, vocab, model_config, training_meta.
  165:    mel_encoder_state_dict is saved as a separate top-level key even though MelEncoder
  174:            "mel_encoder_state_dict": model.mel_enc.state_dict(),

grep -n 'load_state_dict\|load_checkpoint' apollo/scripts/train_smoke.py
  (no output — TRAIN-03 confirmed: no warm-start in smoke train)

grep -n '^models/$' .gitignore
  17:models/

python -m apollo.scripts.train_smoke
  smoke train done: n_pairs=10 n_epochs=50 final_loss=0.0017 type_accuracy=1.0000 checkpoint=models/smoke-20260520T040254Z.pt
```

## Known Stubs

None. All functions are fully implemented. No TODO markers, no placeholder values, no mock returns.

## Threat Flags

No new network endpoints, auth paths, or trust-boundary file I/O. `save_checkpoint` writes to a user-specified local path; `load_checkpoint` reads from a user-specified local path with `weights_only=False` (documented as trusted-local-only in the module docstring — D-24).

## Phase 2 Closure

Phase 2 (Model & Training) is now complete. All 5 plans executed:
- 02-01: MelEncoder CNN (109,184 params confirmed)
- 02-02: ApolloModel decoder transformer (976,384 params total)
- 02-03: ApolloDataset + collate_fn (PAD_ID mask, mel channel dim, int64 cast)
- 02-04: Masked CE loss + train_epoch + run_training + metrics (j >= sep_pos boundary)
- 02-05: Checkpoint serialization + smoke train CLI (TRAIN-04/06 gates met)

Phase 3 (Corpus & Inference) reads checkpoint format: `ApolloModel(**ckpt["model_config"])` + `model.load_state_dict(ckpt["model_state_dict"])`. The Phase 3 LR scheduler plug point (`train_epoch(..., scheduler=warmup_sched)`) is in place from Plan 02-04.

## Self-Check: PASSED

- [x] `apollo/model/train.py` exists (190 lines), contains `save_checkpoint` and `load_checkpoint`
- [x] `apollo/scripts/train_smoke.py` exists (159 lines), contains `def main`
- [x] `tests/test_checkpoint.py` exists (186 lines), contains `test_checkpoint_round_trip_reconstructs_model`
- [x] `tests/test_smoke_train.py` exists (157 lines), contains `assert type_accuracy > 0.95`
- [x] `178bebc` present in git log (RED commit)
- [x] `193cb9c` present in git log (GREEN commit)
- [x] `grep 'weights_only=False' apollo/model/train.py` matches line 190
- [x] `grep 'mel_encoder_state_dict' apollo/model/train.py` matches line 174
- [x] `grep 'load_state_dict\|load_checkpoint' apollo/scripts/train_smoke.py` returns no match (TRAIN-03)
- [x] `grep '^models/$' .gitignore` matches line 17
- [x] 100/100 full suite green
- [x] type_accuracy = 1.0000 (>> 0.95 gate)
- [x] wall_clock = 1.88s (<< 120s budget)
- [x] checkpoint size = 3.7 MB (matches RESEARCH §9 estimate)

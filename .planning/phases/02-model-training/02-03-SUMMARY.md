---
phase: 02-model-training
plan: 3
subsystem: model
tags: [apollo-dataset, collate-fn, packer, tdd, train-01, sequence-packing, pad-mask]
dependency_graph:
  requires:
    - phase: 01-tokenizer-ingest
      provides: artifact dict with pairs[{call_tokens, response_tokens, call_mel, is_heldout}]
    - phase: 02-model-training/02-01
      provides: MelEncoder (needed by __init__.py coexistence)
    - phase: 02-model-training/02-02
      provides: ApolloModel (__init__.py already exports it; packer adds alongside)
  provides:
    - ApolloDataset(artifact, split) — Phase 1 artifact → torch.utils.data.Dataset
    - collate_fn — packs [BOS, call, SEP, resp, EOS, PAD...] → (B, 64) int64 tokens + bool mask + mel
    - apollo.model module-level constants BOS=109, EOS=110, SEP=111, PAD_ID=0, MAX_SEQ_LEN=64
  affects: [02-04, 02-05]
tech_stack:
  added: []
  patterns: [TDD-red-green, length-based-pad-mask, mel-channel-dim-in-collate]
key_files:
  created:
    - apollo/model/packer.py
    - tests/test_packer.py
  modified:
    - apollo/model/__init__.py
key-decisions:
  - "PAD_ID=0 reuses TIME_OFFSET=0 — pad_mask is computed from sequence length L, never from token_ids==0 (RESEARCH pitfall #1)"
  - "mel.unsqueeze(1) in collate_fn adds channel dim (B,1,96,128) required by Conv2d (RESEARCH pitfall #6)"
  - "tokens cast to int64 via .long() in collate_fn — artifact stores int32, nn.Embedding requires LongTensor"
  - "NNNs 000-004 (train) + 006 (heldout) used in fixture — 000-005 are all non-heldout, so 006 was chosen for held_out split coverage"
patterns-established:
  - "length-based pad mask: pad_mask[L:] = True (never token_ids == 0)"
  - "mel channel dim added in collate_fn, not in ApolloDataset.__getitem__"
  - "collate_fn owns the BOS/SEP/EOS wrapping — Dataset returns raw tokens"
requirements-completed: [TRAIN-01]
duration: ~2min
completed: "2026-05-20"
---

# Phase 02 Plan 03: ApolloDataset + collate_fn Summary

**ApolloDataset + collate_fn boundary: filters artifact pairs by split, packs [BOS, call, SEP, resp, EOS, PAD...] to MAX_SEQ_LEN=64 with length-based bool mask and mel.unsqueeze(1) — 10/10 tests green, both RESEARCH-critical fixes confirmed.**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-05-20T03:47:02Z
- **Completed:** 2026-05-20T03:49:13Z
- **Tasks:** 2 (TDD RED + GREEN)
- **Files modified:** 3

## Accomplishments

- `ApolloDataset` correctly filters artifact pairs by `train` / `held_out` / `all` split using the deterministic `is_heldout` field
- `collate_fn` produces the exact `[BOS, call, SEP, resp, EOS, PAD...]` sequence layout, pads to MAX_SEQ_LEN=64, with length-based bool pad mask and mel.unsqueeze(1)
- RESEARCH pitfall #1 pinned by test: `test_pad_mask_is_length_based_not_value_based` places a TIME bin 0 token (value=0) in call_tokens[0] and asserts pad_mask is False at that position
- RESEARCH pitfall #6 confirmed: `grep "unsqueeze(1)"` matches collate_fn mel stacking line
- Full suite 73/73 passing — zero regressions against Phase 1 (46 tests) or 02-01/02-02 (17 tests)

## Test Results

```
tests/test_packer.py::test_dataset_len_train                             PASSED
tests/test_packer.py::test_dataset_len_held_out                          PASSED
tests/test_packer.py::test_dataset_len_all                               PASSED
tests/test_packer.py::test_dataset_getitem_shapes                        PASSED
tests/test_packer.py::test_collate_fn_output_shapes                      PASSED
tests/test_packer.py::test_collate_fn_sequence_layout                    PASSED
tests/test_packer.py::test_pad_mask_is_length_based_not_value_based      PASSED
tests/test_packer.py::test_collate_fn_raises_when_too_long               PASSED
tests/test_packer.py::test_constants_match_vocab                         PASSED
tests/test_packer.py::test_dataloader_integration                        PASSED

10/10 passed in 0.55s
Full suite: 73/73 passed in 2.98s (no regressions)
```

## 2 RESEARCH-Critical Fixes Confirmed

| Fix | Pitfall | Where | Verification |
|-----|---------|-------|-------------|
| `pad_mask[L:] = True` (length-based, NOT `token_ids == 0`) | Pitfall #1 | `packer.py:97` | `test_pad_mask_is_length_based_not_value_based` — value-0 token inside real sequence correctly stays False |
| `torch.stack(mel_list).unsqueeze(1).float()` — adds channel dim for Conv2d | Pitfall #6 | `packer.py:105` | `grep "unsqueeze(1)"` matches; mel.shape verified as (B, 1, 96, 128) in 3 tests |

## Task Commits

TDD execution with RED → GREEN commits:

| Step | Hash | Message |
|------|------|---------|
| RED  | `6d503ad` | `test(02-03): add failing packer contract tests` |
| GREEN | `6ecdcd2` | `feat(02-03): implement ApolloDataset + collate_fn (TRAIN-01)` |

## Files Created / Modified

| File | Lines | Status | Purpose |
|------|-------|--------|---------|
| `apollo/model/packer.py` | 107 | Created | `ApolloDataset` + `collate_fn` with both RESEARCH-critical fixes |
| `tests/test_packer.py` | 246 | Created | 10 contract tests: split filtering, shapes, layout, pad-mask pitfall, constants, DataLoader |
| `apollo/model/__init__.py` | 24 | Modified | Added re-exports of `ApolloDataset`, `collate_fn`, `BOS`, `EOS`, `SEP`, `PAD_ID`, `MAX_SEQ_LEN` |

## Decisions Made

- NNNs 000-004 (non-heldout) + 006 (heldout) used in test fixture rather than 000-005, because `is_heldout("000")` through `is_heldout("005")` are all False — needed NNN 006 to get at least one heldout pair for `test_dataset_len_held_out`.
- No REFACTOR commit needed — packer.py implementation was minimal and matched the spec exactly.

## Deviations from Plan

None — plan executed exactly as written. The implementation in Task 2 matches the RESEARCH §5 code block verbatim (with docstring expansion). The `__init__.py` update reconciles cleanly with Plan 02-02's existing `ApolloModel` export.

## TDD Gate Compliance

- RED gate: `test(02-03)` commit `6d503ad` — all tests fail with `ImportError: cannot import name 'ApolloDataset'`
- GREEN gate: `feat(02-03)` commit `6ecdcd2` — all 10 tests passing; 73/73 full suite green
- REFACTOR gate: not needed — implementation is minimal and correct

## Known Stubs

None. `ApolloDataset.__getitem__` returns real artifact tensors. `collate_fn` performs real packing with real pad masks and real channel-dim mel tensors.

## Threat Flags

No new network endpoints, auth paths, file I/O, or schema changes. Pure in-memory PyTorch Dataset + collate function.

## Next Phase Readiness

- Plan 02-04 (loss masking) can directly import `from apollo.model import ApolloDataset, collate_fn` and use the packed token IDs + pad mask.
- The `SEP` token position in the packed sequence (`ids[1+C] == SEP`) is the exact boundary the loss mask in 02-04 needs to find.
- Plan 02-05 (smoke train) has a working DataLoader path: `DataLoader(ApolloDataset(artifact), batch_size=4, collate_fn=collate_fn)`.

## Self-Check: PASSED

- [x] `apollo/model/packer.py` exists (107 lines)
- [x] `apollo/model/__init__.py` exports `ApolloDataset`, `collate_fn`, `BOS`, `EOS`, `SEP`, `PAD_ID`, `MAX_SEQ_LEN`
- [x] `tests/test_packer.py` exists (246 lines, 10 tests)
- [x] `6d503ad` present in git log (RED commit)
- [x] `6ecdcd2` present in git log (GREEN commit)
- [x] `from apollo.model import ApolloDataset, collate_fn, BOS, EOS, SEP, PAD_ID, MAX_SEQ_LEN` imports successfully
- [x] `print(BOS, EOS, SEP, PAD_ID, MAX_SEQ_LEN)` → `109 110 111 0 64`
- [x] `grep "token_ids == 0" packer.py` returns only docstring/comment lines (no live code)
- [x] `grep "unsqueeze(1)" packer.py` matches line 105 (mel channel dim)
- [x] `grep "pad_mask\[L:\] = True" packer.py` matches line 97 (length-based mask)
- [x] 73/73 tests pass with no regressions

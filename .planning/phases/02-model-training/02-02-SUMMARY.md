---
phase: 02-model-training
plan: 2
subsystem: model
tags: [apollo-model, transformer, mel-prefix, tdd, train-01, train-03, train-05]
dependency_graph:
  requires: [02-01]
  provides: [apollo.model.ApolloModel]
  affects: [02-03, 02-04, 02-05]
tech_stack:
  added: []
  patterns: [decoder-only-transformer, mel-prefix-injection, TDD-red-green]
key_files:
  created:
    - apollo/model/transformer.py
    - tests/test_transformer.py
  modified:
    - apollo/model/__init__.py
decisions:
  - "ApolloModel contains MelEncoder as a submodule (self.mel_enc) so model.parameters() covers both for AdamW optimizer — deviation from D-23/D-25 separate-object approach, but RESEARCH §7 endorses either; submodule is simpler and the plan explicitly requires it"
  - "pos_emb = nn.Embedding(max_seq_len+1, d_model) — size 65 for max_seq_len=64 (RESEARCH pitfall #4 fix)"
  - "TransformerEncoderLayer used (not TransformerDecoderLayer) with norm_first=False, batch_first=True, dropout=0.0"
  - "Float causal src_mask + bool src_key_padding_mask + is_causal=True — UserWarning suppressed via warnings.catch_warnings"
  - "test_uses_transformer_encoder_layer checks for nn.TransformerEncoderLayer (code use) and nn.TransformerDecoderLayer (code use) — not bare string to avoid false positive from docstring comments"
metrics:
  duration: ~2 min
  completed: "2026-05-20T03:44:29Z"
  tasks_completed: 2
  files_created: 2
  files_modified: 1
---

# Phase 02 Plan 02: ApolloModel Implementation Summary

**One-liner:** Decoder-only transformer (4-layer TransformerEncoderLayer, d_model=128) with CNN mel prefix injection at position 0, causal float mask + bool pad mask, pos_emb table size max_seq_len+1 — 976,384 parameters total, 8/8 tests green.

## Files Created / Modified

| File | Lines | Status | Purpose |
|------|-------|--------|---------|
| `apollo/model/transformer.py` | 147 | Created | `ApolloModel` nn.Module — decoder-only transformer with MEL prefix |
| `tests/test_transformer.py` | 204 | Created | 8 contract tests for shape, causality, submodule, pos_emb table size |
| `apollo/model/__init__.py` | 16 | Modified | Added re-export of `ApolloModel` alongside `MelEncoder` |

## Parameter Count Breakdown

| Component | Parameters |
|-----------|-----------|
| `mel_enc` (MelEncoder submodule) | 109,184 |
| `tok_emb` nn.Embedding(256, 128) | 32,768 |
| `pos_emb` nn.Embedding(65, 128) | 8,320 |
| `transformer` (4 × TransformerEncoderLayer) | 793,088 |
| `out_proj` nn.Linear(128, 256) | 33,024 |
| **Total** | **976,384** |

Verified by: `sum(p.numel() for p in ApolloModel().parameters())` = 976,384

## Test Results

```
tests/test_transformer.py::test_instantiates_with_defaults            PASSED
tests/test_transformer.py::test_forward_shape_cpu                     PASSED
tests/test_transformer.py::test_forward_shape_mps                     PASSED
tests/test_transformer.py::test_pos_emb_table_size_is_max_seq_len_plus_one PASSED
tests/test_transformer.py::test_forward_with_padding_mask             PASSED
tests/test_transformer.py::test_uses_transformer_encoder_layer        PASSED
tests/test_transformer.py::test_mel_encoder_is_submodule              PASSED
tests/test_transformer.py::test_causality_is_strict                   PASSED

8/8 passed in 0.66s
Full suite: 63/63 passed in 2.90s (no regressions in Phase 1 or 02-01)
```

## 5 RESEARCH-Critical Fixes Confirmed Present

| Fix | Where | Verification |
|-----|-------|-------------|
| `pos_emb = nn.Embedding(max_seq_len+1, d_model)` — size 65 for default | `transformer.py:67` | `grep "max_seq_len + 1"` + `test_pos_emb_table_size_is_max_seq_len_plus_one` |
| `is_causal=True` + explicit float `mask=causal` on same transformer call | `transformer.py:140-143` | `grep "is_causal=True"` — appears on line 143 alongside `mask=causal` |
| Float `src_mask` + bool `src_key_padding_mask` (UserWarning suppressed) | `transformer.py:134-144` | `warnings.catch_warnings()` context manager wraps transformer call |
| MEL prefix injected via `torch.cat([mel_prefix, tok], dim=1)` — not broadcast | `transformer.py:101` | `test_forward_shape_cpu` + shape check |
| MEL prefix dropped before `out_proj`: `out[:, 1:]` | `transformer.py:149` | Output shape `(B, T, vocab_size)` (not `B, T+1, vocab_size`) confirmed by shape tests |

## Commits Made

| Step | Hash | Message |
|------|------|---------|
| RED  | `689309b` | `test(02-02): add failing ApolloModel contract tests` |
| GREEN | `307aae8` | `feat(02-02): implement ApolloModel (TRAIN-01 scaffold)` |

## Deviations from Plan

### Minor Adjustment (Rule 1 - Bug)

**test_uses_transformer_encoder_layer — string check narrowed to `nn.*` prefix**

- **Found during:** Task 2 (GREEN phase) — test_uses_transformer_encoder_layer failed because the docstring in transformer.py contains the phrase "NOT TransformerDecoderLayer" which triggered the `"TransformerDecoderLayer" not in src` assertion.
- **Fix:** Updated the test to check for `"nn.TransformerEncoderLayer"` (instantiation) and `"nn.TransformerDecoderLayer"` (forbidden code use). This is more precise — it tests that the correct class is actually instantiated, not just mentioned by name in a comment.
- **Files modified:** `tests/test_transformer.py`
- **Commit:** `307aae8` (bundled with GREEN commit)

## TDD Gate Compliance

- RED gate: `test(02-02)` commit `689309b` — all 8 tests fail with `ImportError: cannot import name 'ApolloModel'`
- GREEN gate: `feat(02-02)` commit `307aae8` — all 8 tests passing; 63/63 full suite green
- REFACTOR gate: not needed — implementation is minimal and matches the spec exactly

## Known Stubs

None. `ApolloModel.forward` is fully wired — MelEncoder call, positional embeddings, causal mask, pad mask, transformer stack, prefix drop, and out_proj are all live.

## Threat Flags

No new network endpoints, auth paths, file I/O, or schema changes introduced. Pure in-memory nn.Module.

## Self-Check: PASSED

- [x] `apollo/model/transformer.py` exists (147 lines)
- [x] `apollo/model/__init__.py` exports `ApolloModel`
- [x] `tests/test_transformer.py` exists (204 lines, 8 tests)
- [x] `689309b` present in git log (RED commit)
- [x] `307aae8` present in git log (GREEN commit)
- [x] `from apollo.model import ApolloModel` imports successfully
- [x] `ApolloModel().forward(zeros(2,64), randn(2,1,96,128)).shape` = `torch.Size([2, 64, 256])`
- [x] Total parameter count = 976,384
- [x] `grep "TransformerEncoderLayer" apollo/model/transformer.py` returns match
- [x] `grep "nn.TransformerDecoderLayer" apollo/model/transformer.py` returns no match
- [x] `grep "max_seq_len + 1" apollo/model/transformer.py` returns match
- [x] `grep "is_causal=True" apollo/model/transformer.py` returns match

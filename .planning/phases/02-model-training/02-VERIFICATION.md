---
phase: 02-model-training
verified: 2026-05-20T04:13:20Z
status: passed
score: 8/8 must-haves verified
overrides_applied: 0
re_verification: false
---

# Phase 02: Model Training Verification Report

**Phase Goal:** Build the complete model training pipeline — MelEncoder, ApolloModel transformer, ApolloDataset + collate_fn, masked response-only loss, and checkpoint I/O — so that a smoke-train pass on 4 synthetic pairs achieves type_accuracy > 0.95 and completes in under 120 seconds on CPU/MPS.
**Verified:** 2026-05-20T04:13:20Z
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | MelEncoder(d_model=128) forward on (B,1,96,128) returns (B,128) on CPU and MPS | VERIFIED | Live check: output shape torch.Size([2, 128]); test_forward_shape_cpu + test_forward_shape_mps both pass |
| 2 | MelEncoder parameter count is exactly 109,184 | VERIFIED | Live check: sum(p.numel()) = 109184; test_parameter_count passes |
| 3 | MelEncoder gradients flow after backward pass | VERIFIED | test_gradients_flow passes; test_mel_encoder_params_update confirms param update after train_epoch |
| 4 | ApolloModel forward returns (B,T,vocab_size) on CPU and MPS | VERIFIED | Live check: torch.Size([2, 64, 256]); test_forward_shape_cpu + test_forward_shape_mps pass |
| 5 | Loss is masked to response positions only (j >= sep_pos, not j > sep_pos) | VERIFIED | test_loss_mask_uses_geq_sep_pos, test_loss_mask_includes_first_response_token, test_loss_mask_excludes_bos_call_sep all pass; live grep confirms j_range >= sep_pos.unsqueeze(1) in train.py line 76 |
| 6 | Smoke train on 10 mock pairs achieves type_accuracy > 0.95 | VERIFIED | test_smoke_train_hits_accuracy_gate passes; actual value type_accuracy=1.0000 |
| 7 | Smoke train completes in under 120 seconds on MPS | VERIFIED | test_smoke_train_wall_clock_under_120s passes; actual wall clock = 1.88s |
| 8 | Checkpoint round-trip reconstructs ApolloModel bit-identically with all 5 required keys | VERIFIED | test_checkpoint_round_trip_reconstructs_model + test_checkpoint_keys pass; mel_encoder_state_dict is a separate top-level key |

**Score:** 8/8 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `apollo/model/__init__.py` | Package re-exports MelEncoder, ApolloModel, ApolloDataset, collate_fn, all training functions | VERIFIED | 41 lines; all 14 symbols re-exported and importable |
| `apollo/model/mel_encoder.py` | MelEncoder nn.Module (Conv2d→ReLU→MaxPool ×3→AdaptiveAvgPool→FC) | VERIFIED | 54 lines; exact D-01 architecture, 109,184 params |
| `apollo/model/transformer.py` | ApolloModel with MEL prefix, causal mask, pos_emb=max_seq_len+1, enable_nested_tensor=False | VERIFIED | 153 lines; all 5 RESEARCH critical fixes present; TransformerDecoderLayer absent |
| `apollo/model/packer.py` | ApolloDataset + collate_fn; length-based pad mask; mel.unsqueeze(1) | VERIFIED | 107 lines; token_ids==0 appears only in docstring/comments, not live code; pad_mask[L:]=True is live code |
| `apollo/model/train.py` | compute_masked_loss, train_epoch, run_training, get_device, save_checkpoint, load_checkpoint | VERIFIED | 190 lines; j>=sep_pos boundary confirmed; no torch.compile; no load_state_dict; weights_only=False in load_checkpoint |
| `apollo/model/metrics.py` | token_category, compute_type_accuracy | VERIFIED | 50 lines; 6-bucket categorization; response-only mask |
| `apollo/scripts/train_smoke.py` | End-to-end CLI: mock pairs→ingest→train→eval→save checkpoint | VERIFIED | 159 lines; def main + if __name__=="__main__"; no load_state_dict (TRAIN-03) |
| `tests/test_mel_encoder.py` | 6 contract tests | VERIFIED | 116 lines; all 6 pass |
| `tests/test_transformer.py` | 8 contract tests including test_pos_emb_table_size_is_max_seq_len_plus_one | VERIFIED | 8 tests; all pass |
| `tests/test_packer.py` | 10 contract tests including test_pad_mask_is_length_based_not_value_based | VERIFIED | 10 tests; all pass |
| `tests/test_train.py` | 15 tests including test_loss_mask_uses_geq_sep_pos | VERIFIED | 15 tests; all pass |
| `tests/test_checkpoint.py` | 8 round-trip and key-structure tests | VERIFIED | 8 tests; all pass |
| `tests/test_smoke_train.py` | 4 tests including TRAIN-04 hard gate assertion | VERIFIED | 4 tests; all pass; type_accuracy=1.0000 |
| `.gitignore` | Contains models/ | VERIFIED | Line 17: models/ |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| ApolloModel | MelEncoder | self.mel_enc submodule | VERIFIED | model.parameters() covers mel_enc; confirmed by test_mel_encoder_is_submodule and test_mel_encoder_params_update |
| train_epoch | ApolloModel.forward | model(token_ids, mel, key_padding_mask=pad_mask) | VERIFIED | train.py line 112 |
| compute_masked_loss | token_ids SEP position | (token_ids == sep_id).long().argmax(dim=1) | VERIFIED | train.py lines 72-76; boundary is j_range >= sep_pos |
| collate_fn | BOS/EOS/SEP constants | from apollo.tokenizer import Vocab | VERIFIED | packer.py lines 18-25; constants match Vocab values |
| train_smoke.main | run_training | run_training(model, dl, n_epochs=n_epochs, lr=lr, device=device) | VERIFIED | train_smoke.py calls run_training; no load_state_dict present |
| save_checkpoint | mel_encoder_state_dict | model.mel_enc.state_dict() | VERIFIED | train.py line 174; separate top-level key per D-23 |
| load_checkpoint | torch.load | weights_only=False | VERIFIED | train.py line 190 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| train_epoch | loss | compute_masked_loss(logits, token_ids) | Yes — logits from ApolloModel.forward, token_ids from DataLoader | FLOWING |
| _evaluate_type_accuracy | type_accuracy | compute_type_accuracy across all DataLoader batches | Yes — aggregates numerators/denominators, not averaging averages | FLOWING |
| test_smoke_train_hits_accuracy_gate | type_accuracy | ApolloModel trained on 10 mock pairs, 50 epochs | Yes — 1.0000 (>0.95 gate) | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| MelEncoder param count | python -c "sum(p.numel() for p in MelEncoder(128).parameters())" | 109184 | PASS |
| ApolloModel output shape | python -c "ApolloModel()(zeros(2,64,long), randn(2,1,96,128)).shape" | torch.Size([2, 64, 256]) | PASS |
| mel_enc is submodule | any(n.startswith('mel_enc.') for n,_ in ApolloModel().named_parameters()) | True | PASS |
| pos_emb table size | ApolloModel().pos_emb.num_embeddings | 65 (max_seq_len+1 for max_seq_len=64) | PASS |
| Full test suite | pytest tests/ -q | 100 passed, 44 warnings in 12.48s | PASS |
| get_device() | from apollo.model.train import get_device; get_device() | mps | PASS |
| Constants | from apollo.model import BOS, EOS, SEP, PAD_ID, MAX_SEQ_LEN | 109 110 111 0 64 | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| COND-02 | 02-01 | Small mel encoder compresses mel tensor into conditioning embedding | SATISFIED | MelEncoder(d_model=128) implemented in apollo/model/mel_encoder.py; 109,184 params; 6/6 tests pass |
| COND-03 | 02-01 | Mel encoder is jointly trained, not frozen | SATISFIED | MelEncoder is a submodule of ApolloModel (self.mel_enc); AdamW(model.parameters()) covers it; test_mel_encoder_params_update confirms param update |
| TRAIN-01 | 02-02, 02-03 | Training samples pack as [BOS, call, SEP, response, EOS] | SATISFIED | collate_fn produces exact layout; test_collate_fn_sequence_layout verifies positions |
| TRAIN-02 | 02-04 | Loss masked to response tokens only | SATISFIED | compute_masked_loss uses j >= sep_pos boundary; test_loss_mask_uses_geq_sep_pos confirms boundary; response CE=0.0021 vs call CE=3.2011 after 30 epochs |
| TRAIN-03 | 02-04, 02-05 | Trained from scratch, no warm-start | SATISFIED | No load_state_dict in train.py or train_smoke.py; test_random_init_no_checkpoint_load and test_smoke_train_runs_from_random_init both pass |
| TRAIN-04 | 02-05 | Smoke train >= 10 mock pairs reaches > 95% type-accuracy | SATISFIED | test_smoke_train_hits_accuracy_gate: type_accuracy=1.0000 > 0.95 (hard assert) |
| TRAIN-05 | 02-04, 02-05 | Trains locally on MPS in reasonable wall-clock | SATISFIED | test_smoke_train_wall_clock_under_120s: 1.88s on MPS; test_train_step_runs_on_mps passes |
| TRAIN-06 | 02-05 | Checkpoints save model state + mel encoder + tokenizer config under models/ | SATISFIED | save_checkpoint writes 5 keys (model_state_dict, mel_encoder_state_dict, vocab, model_config, training_meta); test_checkpoint_keys confirms; models/ in .gitignore |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| packer.py | 8, 71 | "token_ids == 0" appears | Info | Docstring/comment only — no live code uses value-based mask; live code correctly uses pad_mask[L:]=True |
| REQUIREMENTS.md | 27-39 | COND-02, COND-03, TRAIN-02..06 still marked [ ] (pending) | Info | Documentation lag only — all requirements are implemented and tested; does not affect code |

No blockers found. The "token_ids == 0" pattern in packer.py appears only in NEVER-do documentation (lines 8 and 71), not in live execution code. The live mask logic on line 97 (pad_mask[L:] = True) is correctly length-based.

### Human Verification Required

None. All phase goals are verifiable programmatically and confirmed by the full test suite.

### Gaps Summary

No gaps. All 8 must-have truths are verified, all artifacts are substantive and wired, data flows end-to-end, and the test suite passes at 100/100. The only notable item is that REQUIREMENTS.md still marks COND-02, COND-03, and TRAIN-02..06 as pending — this is a documentation update needed in REQUIREMENTS.md, not a code gap.

---

_Verified: 2026-05-20T04:13:20Z_
_Verifier: Claude (gsd-verifier)_

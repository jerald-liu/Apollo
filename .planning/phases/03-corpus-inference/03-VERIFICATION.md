---
phase: 03-corpus-inference
verified: 2026-05-19T00:00:00Z
status: human_needed
score: 7/8 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Run generate.py with a real trained checkpoint and a real Ableton pair, open response_001.mid in Ableton, confirm it is musically coherent"
    expected: "response_001.mid opens and plays back without MIDI errors; notes have correct pitches, velocities, and durations"
    why_human: "Cannot verify musical coherence or correct MIDI playback in Ableton programmatically; untrained checkpoint produces noise, so a real trained checkpoint is needed"
---

# Phase 3: Corpus & Inference Verification Report

**Phase Goal:** Corpus stub + inference CLI + production training script — user can author pairs and run generate.py to hear model outputs.
**Verified:** 2026-05-19T00:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | data/pairs/ exists as a tracked directory in the repo | VERIFIED | Directory exists; `.gitkeep` confirmed at `data/pairs/.gitkeep` |
| 2 | Authoring conventions are documented so the human can produce conforming pairs | VERIFIED | `data/pairs/CORPUS-CONVENTIONS.md` exists with all required content (120 BPM, DATA-05, DATA-02, D-01..D-07, Ableton workflow, 0.5–1.5s gesture length) |
| 3 | Conventions cover BPM, preset variety, key/scale, gesture length, file naming, and the ≥30 minimum | VERIFIED | All 7 conventions (D-01..D-07) present in CORPUS-CONVENTIONS.md with explicit table |
| 4 | Running generate.py with a checkpoint, call.mid, and call.wav produces a response_NNN.mid file | VERIFIED | test_generate_smoke_creates_response_midi PASSED; response_001.mid created |
| 5 | --max-tokens, --temperature, --top-k, --n CLI flags work without code changes | VERIFIED | test_generate_temperature_topk_flags PASSED; all 4 flags confirmed in argparse |
| 6 | Multiple invocations produce non-overlapping response_001.mid, response_002.mid, ... filenames | VERIFIED | test_generate_n_samples_naming PASSED; _next_response_path finds next available index |
| 7 | Invalid tokens emitted by the model are skipped, not crashed on | VERIFIED | _decode_with_invalid_skip walks 4-groups individually, catches ValueError per group |
| 8 | Running generate.py produces a response.mid parseable in Ableton (real end-to-end) | NEEDS HUMAN | Unit tests use untrained checkpoint; musical correctness requires human ear test |

**Score:** 7/8 truths verified (8th deferred to human)

### Deferred Items

No items are addressed in later milestone phases. Phase 4 (Evaluation Loop) adds a rubric but does not close the gap on human playback verification of generate.py output.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `data/pairs/.gitkeep` | Tracked empty directory | VERIFIED | Exists, zero bytes |
| `data/pairs/CORPUS-CONVENTIONS.md` | Human authoring guide | VERIFIED | 13 grep matches for required strings; all D-01..D-07 present |
| `apollo/scripts/generate.py` | Autoregressive inference CLI, ≥120 lines, def main | VERIFIED | 215 lines; all 6 functions present; imports clean |
| `tests/test_generate.py` | 5 passing tests | VERIFIED | All 5 tests named and passing |
| `apollo/scripts/train.py` | Production training CLI, ≥150 lines, def main | VERIFIED | 224 lines; main + _evaluate_heldout_loss present; imports clean |
| `tests/test_train_real.py` | 5 passing tests | VERIFIED | All 5 tests named and passing |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| apollo/scripts/generate.py | apollo/model/train.py:load_checkpoint | checkpoint reconstruction | WIRED | grep confirmed `load_checkpoint` import + usage at line with `ckpt = load_checkpoint(...)` |
| apollo/scripts/generate.py | apollo/tokenizer/decoder.py:decode_tokens | response token decode | WIRED | grep confirmed `decode_tokens` import + usage inside `_decode_with_invalid_skip` |
| apollo/scripts/generate.py | apollo/ingest/audio.py:MelExtractor | call.wav mel extraction | WIRED | grep confirmed `MelExtractor` import + instantiation + call |
| apollo/scripts/generate.py | apollo/tokenizer/encoder.py:Tokenizer | call MIDI token encoding for prefix | WIRED | grep confirmed `Tokenizer` import + instantiation + `encode()` call |
| apollo/scripts/train.py | apollo/model/train.py:train_epoch | scheduler= keyword argument | WIRED | Lines 168–170: `train_epoch(model, train_loader, optimizer, device, scheduler=scheduler)` — multiline call confirmed by Read |
| apollo/scripts/train.py | torch.optim.lr_scheduler.OneCycleLR | scheduler construction with pct_start=0.05 | WIRED | grep confirmed `OneCycleLR`, `pct_start=0.05`, `anneal_strategy="cos"` |
| apollo/scripts/train.py | apollo/model/train.py:save_checkpoint | checkpoint save with run-NN-timestamp.pt naming | WIRED | grep confirmed `save_checkpoint` + `run-{args.iteration:02d}-{timestamp}.pt` literal |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| apollo/scripts/generate.py | `generated` (token IDs) | `_sample_one_response` → model logits → torch.topk + torch.multinomial | Yes — model forward pass produces real logits; sampling is genuine | FLOWING |
| apollo/scripts/generate.py | `notes` | `_decode_with_invalid_skip` → `decode_tokens` → Note objects | Yes — token IDs decoded to Note dataclasses | FLOWING |
| apollo/scripts/train.py | `train_loss` | `train_epoch` → masked CE loss over DataLoader batches | Yes — real gradient-based training loop | FLOWING |
| apollo/scripts/train.py | `held_loss` | `_evaluate_heldout_loss` → compute_masked_loss over held-out DataLoader | Yes — real evaluation over held-out split | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| generate.py imports cleanly | `venv/bin/python -c "from apollo.scripts import generate"` | Exit 0, no output | PASS |
| train.py imports cleanly | `venv/bin/python -c "from apollo.scripts import train"` | Exit 0, no output | PASS |
| 10/10 phase 3 tests pass | `venv/bin/python -m pytest tests/test_generate.py tests/test_train_real.py -q` | 10 passed | PASS |
| Full suite: 110/110 pass | `venv/bin/python -m pytest -x -q` | 110 passed, 58 warnings | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| DATA-05 | 03-01-PLAN.md | Corpus reaches ≥30 authored pairs before first real training run | PARTIAL | Directory structure + CORPUS-CONVENTIONS.md delivered (code deliverable done). The ≥30 pairs themselves are human Ableton work — pending human authoring. REQUIREMENTS.md correctly marks DATA-05 as unchecked. |
| INFER-01 | 03-02-PLAN.md | generate.py accepts call.mid + call.wav and emits response.mid | VERIFIED | test_generate_smoke_creates_response_midi PASSED; response_001.mid confirmed created |
| INFER-02 | 03-02-PLAN.md | Response length configurable (max events or max seconds) | VERIFIED | --max-tokens flag with default 24; test_generate_temperature_topk_flags PASSED |
| INFER-03 | 03-02-PLAN.md | Sampling supports temperature and top-k controls | VERIFIED | --temperature (default 0.8) and --top-k (default 10) flags confirmed; torch.topk + torch.multinomial verified in source |
| INFER-04 | 03-02-PLAN.md | Optional: sample N responses per call | VERIFIED | --n flag (default 1); test_generate_n_samples_naming PASSED with --n 3 producing response_002..004.mid |

**Note on 03-03-PLAN.md requirements field:** Plan 03-03 lists `requirements: []` (empty). It delivers `apollo/scripts/train.py` which supports the DATA-05 and INFER-* requirements instrumentally (the production training script the phase goal references) but does not claim ownership of additional requirement IDs. No orphaned requirements detected — all 5 phase requirement IDs (DATA-05, INFER-01..INFER-04) are fully accounted for across Plans 01 and 02.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| apollo/scripts/train.py | 163 | Comment: `# 5. Train loop — do NOT call scheduler.step() here` | Info | Explanatory comment, not a stub. `scheduler.step()` in comment only — no double-step in outer loop. |

No blockers. No stubs. No TODO/FIXME/placeholder patterns in any Phase 3 file.

### Human Verification Required

#### 1. End-to-End Generate Test With Real Trained Checkpoint

**Test:** Train the model on a real authored corpus (or a large mock corpus), produce a checkpoint, then run:
```
venv/bin/python -m apollo.scripts.generate <checkpoint.pt> data/pairs/001/call.mid data/pairs/001/call.wav
```
Open `data/pairs/001/response_001.mid` in Ableton. Assign an Operator preset and play back.

**Expected:** The response MIDI plays without import errors; notes have valid pitches, velocities, and durations; the file is not empty (unless the model genuinely generated no valid 4-groups, which is acceptable for an untrained model).

**Why human:** Unit tests exercise the full code path with an untrained checkpoint. Verifying that the output is musically playable in Ableton, and that the MIDI structure is well-formed for a real DAW, requires human ear and DAW import. Additionally, confirming that `pretty_midi`-written MIDI round-trips through Ableton without format warnings requires a live check.

### Gaps Summary

No blocking gaps were found. All six code artifacts exist, are substantive, are wired to their dependencies, and have data flowing through them. All 10 phase-specific tests pass; the full 110-test suite passes.

The one human verification item is the real end-to-end playback test — this is expected at this stage (an untrained checkpoint cannot produce musical output). Once the human authors ≥30 pairs and runs a real training run, the generate.py → Ableton playback path should be tested manually.

DATA-05 is correctly marked as partially satisfied: the code deliverable (directory + authoring guide) is complete; the human authoring of ≥30 pairs is pending and is not a code gap.

---

_Verified: 2026-05-19T00:00:00Z_
_Verifier: Claude (gsd-verifier)_

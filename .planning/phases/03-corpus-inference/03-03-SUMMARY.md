---
phase: 03-corpus-inference
plan: 03
status: complete
started: 2026-05-19T00:00:00Z
completed: 2026-05-19T00:00:00Z
duration_min: 6
---

# 03-03 Summary: Production Training CLI

## What Was Built

`apollo/scripts/train.py` — full production training CLI with OneCycleLR, held-out tracking, and D-10 naming. `tests/test_train_real.py` — 5 tests covering smoke, held-out logging, iteration naming, warning, and no-csv flag.

## Key Files

### Created
- `apollo/scripts/train.py` — production training CLI
- `tests/test_train_real.py` — 5 tests all passing

## Implementation Notes

- **Scheduler NOT double-stepped**: `train_epoch` calls `scheduler.step()` per-batch (confirmed line 119 of apollo/model/train.py). `train.py` does not call `scheduler.step()` in the outer epoch loop.
- **Split verified**: With nnn `000`–`006`, pair `006` is held out (sha1 hash mod 5 == 0). 7 pairs → 6 train + 1 held_out, sufficient for both DataLoaders.
- **Collate order**: `(token_ids, pad_mask, mel)` — matches packer.py return signature.
- **`type_accuracy: 0.0`** in `training_meta` — Phase 3 doesn't compute it; Phase 2's smoke train covers that metric.

## Verification

```
✓ apollo/scripts/train.py exists with main(argv=None) -> int
✓ _evaluate_heldout_loss has @torch.no_grad() decorator
✓ OneCycleLR with pct_start=0.05, anneal_strategy="cos"
✓ No explicit scheduler.step() in outer epoch loop
✓ Checkpoint pattern: run-{args.iteration:02d}-{timestamp}.pt
✓ WARNING emitted to stderr when n_pairs < 30 (non-aborting)
✓ Final summary: "train done: n_pairs=..." prefix
✓ CLI flags: --epochs, --lr, --batch-size, --log-every, --iteration, --output-dir, --log-dir, --seed, --no-csv
✓ 5/5 tests pass
```

## Self-Check: PASSED

train.py runs end-to-end on a mock corpus, saves a run-NN-timestamp.pt checkpoint, logs held-out loss. Phase 4 evaluation can invoke this script repeatedly across iterations.

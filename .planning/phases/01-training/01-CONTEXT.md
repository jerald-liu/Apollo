# Phase 1: Training - Context

**Gathered:** 2026-05-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Resolve the Modal billing blocker, re-launch both training runs in parallel, monitor to 80K steps, and confirm best checkpoints are saved to the `apollo-checkpoints` Modal volume.

This phase is operational, not architectural — configs are already correct and tested locally. The work is launching, watching, and confirming.

</domain>

<decisions>
## Implementation Decisions

### Run Strategy
- **D-01:** Launch v3 (mel) and v4 (streaming) in **parallel** — both at the same time via `make modal-train CONFIG=configs/v3_mel.yaml` and `make modal-train CONFIG=configs/v4_streaming.yaml`.
- **D-02:** Both runs use existing, tested configs — no config changes needed before launch.

### Billing
- **D-03:** Modal billing limit is **already resolved** — runs can be launched immediately. No waiting or billing escalation steps needed.

### Scope
- **D-04:** Both runs must complete — v3 validates mel conditioning against v2 baseline (2.1641), v4 validates streaming vocab. Neither is optional.

### Claude's Discretion
- Monitoring approach during training (Modal console logs vs. WandB — `use_wandb: false` in both configs, can keep as-is)
- Early stopping / intervention criteria if a run diverges
- Verification steps to confirm checkpoints are correctly saved to Modal volume before handing off to Phase 2

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Training Configs
- `configs/v3_mel.yaml` — v3 mel conditioning config (batch=64, lr=4.2e-4, max_steps=80K, no compile)
- `configs/v4_streaming.yaml` — v4 streaming vocab config (batch=256, lr=6.0e-4, compile=true, max_steps=80K, vocab_size=259)

### Training Infrastructure
- `scripts/train.py` — Training loop with checkpoint saving logic (save_interval=2K steps, eval_interval=500, saves `best`, `latest`, `step_N` tags)
- `modal_train.py` — Modal entrypoint for cloud A100 training
- `Makefile` — `modal-train` target for launching Modal runs

### Requirements
- `.planning/REQUIREMENTS.md` — TRAIN-01 through TRAIN-04 are the acceptance criteria for this phase

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Makefile` `modal-train` target: `make modal-train CONFIG=<path>` launches a Modal A100 run — already tested
- `modal_train.py`: Cloud entrypoint, handles data mounting, checkpoint volume attachment to `apollo-checkpoints`

### Established Patterns
- Checkpointing: `save_checkpoint()` in `scripts/train.py` saves to `config.output_dir` with tag (`best`, `latest`, `step_{N}`). `best` is saved when val loss improves.
- Val loss logged every 500 steps via `eval_interval`; step checkpoints every 2000 via `save_interval`

### Integration Points
- Checkpoints flow to `apollo-checkpoints` Modal volume → `make pull-checkpoints` retrieves them locally for Phase 2 evaluation
- Phase 2 depends on `models/checkpoint_v3_best.pt` and `models/checkpoint_v4_best.pt` existing locally

</code_context>

<specifics>
## Specific Ideas

- Runs are tested and configs are confirmed correct — no debugging expected on launch
- v3 target: val loss < 2.1641 (beat v2 augmented baseline at 50K steps)
- v4 target: val loss < 2.3 at 80K steps (healthy descent, even if not beating v2 — different vocab)
- v4 augmentation is intentionally disabled (pitch/velocity aug incompatible with 259-token streaming vocab offsets)

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 01-training*
*Context gathered: 2026-05-13*

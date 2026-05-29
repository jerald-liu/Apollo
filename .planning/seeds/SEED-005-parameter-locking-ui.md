---
id: SEED-005
status: dormant
planted: 2026-05-20
planted_during: v2.0 / Phase 02 (model-training) complete, before any UI phase
trigger_when: First UI/frontend phase is scoped, or user requests interactive generation controls
scope: Small-to-Medium
---

# SEED-005: Parameter locking in the generation UI

## Why This Matters

When Apollo has a UI, the user will want to constrain generation along specific musical dimensions while letting the model vary others — "keep the pitch in this octave but let rhythm vary," "lock the duration grid but let velocity move," "fix the register, surprise me on contour." This is the difference between a generative toy and a usable compositional tool: the user steers, the model fills the gaps.

The factored vocab (pitch / velocity / time-shift / duration as separate token classes) makes this clean to implement — much cleaner than in models that emit interleaved compound tokens.

## Approach

**Constrained decoding via logit masking.** At sample time, for each token class the user has locked:

- Identify the locked range/value (e.g. pitch ∈ [C3, C5], duration ∈ {1/16, 1/8})
- When the next token to emit is of that class, mask the logits of all out-of-range token IDs to `-inf` before softmax
- Sample normally from the remaining distribution

No retraining required. The token-class structure of the vocab is what makes this tractable — masking is per-class, not per-arbitrary-pattern.

## UI Considerations

- **Lockable dimensions (v1 vocab):** pitch (range), velocity (range), time-shift (grid resolution), duration (grid or specific values).
- **Lockable dimensions (future vocab):** pitch bend depth, mod wheel range, specific CCs — same masking pattern applies once those tokens exist.
- **Visual affordance:** each dimension shown as a slider/range control with a "lock" toggle. Locked controls visibly freeze; unlocked controls show the sampled distribution after each generation.
- **Interaction with temperature/top-p:** locks compose with sampling controls. A locked pitch range + high temperature = "wild within this register."
- **Failure mode to design for:** over-constrained locks (e.g. only one pitch allowed) collapse the model to deterministic output and may produce musically poor results. UI should warn when locks make the feasible set degenerate.

## Open Questions

1. **Lock granularity.** Per-token-class is the minimum. Per-position (lock note 3 of the response to specifically C4) is a more advanced feature — defer unless explicitly asked.
2. **Lock persistence.** Do locks persist across generations in a session, or reset? Probably persist with a "clear all locks" button.
3. **Interaction with bidirectional generation ([[SEED-004-bidirectional-chaining]]).** When chaining, do locks apply uniformly across all turns, or per-turn? Per-turn is more powerful but more UI surface.
4. **Pre-generation preview.** Can we show the user what's been masked before they hit generate? Useful for the degenerate-lock warning above.

## When to Surface

**Trigger A:** First UI/frontend phase is scoped (any phase introducing a non-CLI interface).
**Trigger B:** User asks how to constrain generation interactively.

Present during `/gsd-ui-phase` discussion or whenever UI design questions come up.

## Scope Estimate

**Small-to-Medium** — Backend changes are minimal (a logit-masking pass in the sampler that reads a lock spec). Most of the work is UI: the controls, the visual state, the warning system for degenerate locks.

If shipped alongside the first UI phase: incremental cost is small.
If shipped standalone later: requires the UI scaffolding to exist first.

## Breadcrumbs

- `apollo/model/sampling.py` (future, Phase 3) — temperature + nucleus sampler; logit-masking hook lives here
- `apollo/data/tokenizer.py` — vocab structure; token-class boundaries are what masking targets
- `apollo/inference/generate.py` (future, Phase 3) — CLI; may grow a `--lock-pitch C3:C5` style flag as a CLI precursor before the UI exists
- `.planning/seeds/SEED-004-bidirectional-chaining.md` — interaction with multi-turn generation

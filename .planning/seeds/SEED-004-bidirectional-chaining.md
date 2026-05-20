---
id: SEED-004
status: dormant
planted: 2026-05-20
planted_during: v2.0 / Phase 02 (model-training) complete, before Phase 03
trigger_when: After v1 ships, or earlier if user requests theme-chaining workflow
scope: Medium
---

# SEED-004: Bidirectional generation + theme chaining

## Why This Matters

Apollo v1 generates `response | call`. Inverting the direction — generating `call | response` — unlocks a chaining workflow: any phrase the user plays (or the model emits) can serve as either prompt or completion, and themes can be built by alternating forward/reverse generation off the previous turn's output. This is the computational basis for "phrases that build off themselves."

Without inversion, the user is stuck in a one-shot interaction. With it, Apollo becomes a conversational partner across an arbitrarily long musical exchange.

## Approach

**Single bidirectional model with a direction token** is the right design. Reject alternatives:

- ❌ Two models (forward + reverse): 2× checkpoints, 2× training cost, no benefit.
- ❌ Run causal model "backwards" at inference: impossible — model has only learned `p(response|call)`.
- ✅ One model, pack both orientations during training:
  - `[BOS, DIR_FWD, call_tokens, SEP, response_tokens, EOS]`
  - `[BOS, DIR_REV, response_tokens, SEP, call_tokens, EOS]`
  - Loss masked to the post-SEP side either way.

Effective doubling of training data, single artifact, clean inference path.

## Open Questions

1. **Mel conditioning under reversal.** Today's prefix is `call.wav` mel features. In reverse mode the *prompt* side is the response, so the mel encoder must see response audio. **Implication for corpus:** every pair needs `response.wav` rendered too — adds an Ableton bounce step per pair (or an automated render pass). Decide at planning time whether to require this for all new pairs or only for pairs authored after this seed surfaces.

2. **Vocab impact.** Adding `DIR_FWD` / `DIR_REV` as tokens. Per the v1 vocab-extensibility constraint, this must be done in a reserved slot so existing checkpoints don't become invalid. If reserved slots aren't available, this becomes a vocab-breaking change and requires a fresh train.

3. **Chain drift.** Generated → prompt → generated → ... will wander off the original timbre/register without anchoring. Worth a rubric dimension when this ships: "after N turns, does the chain still feel coherent with turn 0?"

4. **Composability with SEED-002 (hierarchical).** Theme-level call-and-response and bidirectional gesture generation are complementary — a theme's internal gestures could be generated bidirectionally while the theme-level model handles structure. Don't ship in the same milestone; sequence carefully.

## When to Surface

**Trigger A:** User explicitly requests reverse generation or theme chaining workflow.
**Trigger B:** After v1 ships and active-learning loop is validated.

Present during `/gsd-new-milestone` when:
- Milestone scope mentions chaining, themes, multi-turn, or "build off itself"
- User notes that one-shot interaction feels limiting

## Scope Estimate

**Medium** — Single milestone, no architecture rewrite. Requires:
- Vocab extension (2 direction tokens) — check reserved-slot policy
- Training data repacking: emit both orientations from each pair
- Mel encoder retraining if response audio wasn't in v1's training set
- Corpus convention update: `response.wav` becomes required (or automated render)
- Inference CLI: `--direction {fwd,rev}` flag in `generate.py`
- Eval rubric: add multi-turn chain coherence dimension

## Breadcrumbs

- `apollo/data/tokenizer.py` — vocab structure and reserved slots; check if 2 token IDs are available without breaking checkpoints
- `apollo/model/model.py` — ApolloModel packing; the `[BOS, call, SEP, response, EOS]` layout that becomes orientation-conditional
- `apollo/data/dataset.py` — ApolloDataset + collate_fn; the place where both orientations would be emitted per pair
- `.planning/PROJECT.md` — "Core Value" section; chaining extends the active-learning loop
- `.planning/seeds/SEED-002-hierarchical-call-and-response.md` — companion seed; coordinate sequencing

---
id: SEED-010
status: dormant
planted: 2026-06-02
planted_during: v2.0 / Phase 05 (local-app-browser-synth) planning
trigger_when: When the active-learning loop plateaus AND error analysis shows the model failing to reuse the user's recurring motifs; OR independently, any time structural-validity defects appear in generated responses (hard-grammar mask is a standalone cheap win)
scope: Medium
---

# SEED-010: Trie-like automata as composable decode-time memory layers

Trie-like automata as **composable, non-differentiable decode-time overlays** for Apollo — a per-instance extension layer, *orthogonal to the model weights*, that travels with an Apollo instance and updates without retraining. The trie is the shared substrate; two distinct modes differ in **readout** and **origin**:

| | Stochastic (style-inspired) | Restrictive (rules / grammar) |
|---|---|---|
| Structure | Weighted automaton — PPM / variable-order Markov model (VLMM) | Unweighted acceptor — DFA / FSM |
| Readout | counts → next-token probabilities | membership → accept/reject |
| Decoder interface | **soft**: interpolate / add into logits (tunable weight) | **hard**: 0/1 legality mask multiplied onto logits |
| Origin | **learned** from the corpus | **authored** a priori (NOT learned) |

They **compose as layers**: `legal-mask ∘ style-bias ∘ model` — a constraint layer and a preference layer, both bolted onto decoding rather than baked into weights.

## Why This Matters

- **Decouples personalization from the weights.** A small, inspectable, updatable per-user memory that grows with the corpus and survives retrains — directly aligned with Apollo's local-first, per-instance ethos. This portability is the real prize, more than any single accuracy bump.
- **Targets the regime neural models are weakest in.** In the <100-example corpus (ship gate ≥30 pairs), transformers under-recall exact motifs. An explicit memory gives exact-match recall the net lacks — the one place "performance" can actually improve (speed is *not* a bottleneck: ~1M params, ~2s inference).
- **The hard grammar mask is a cheap standalone win.** Structural validity (4-token note-grammar order, duration-in-range, monophonic non-overlap, length bounds) can be *guaranteed* with an authored FSM and zero training — strictly better than learning a validity acceptor.

## Critical Design Constraints (learned during the 2026-06-02 discussion)

- **Stochastic mode MUST live in transposition-invariant / relative space** (pitch intervals + rhythm). An absolute-token trie fragments to singletons on a ~30-pair corpus and ignores the call-conditioning (`P(response | call, timbre)`) that *defines* the task. The strongest "memory artifact" variant may actually be **retrieval over `(call-embedding → response)` keyed by call similarity**, which respects the conditioning a raw token-trie throws away. Pedigree: IDyOM-style VLMM/PPM melodic-expectation models.
- **Restrictive mode must be AUTHORED, not learned.** Learning a restrictive acceptor from the tiny corpus overfits into a gatekeeper that rejects valid-but-unseen responses. Specify the FSM from the vocab grammar (or an explicit imposed style rule).

## Why Defer (not v1)

v1's thesis is *the active-learning loop is the product* (ship gate = two consecutive iterations both improving held-out call-response-fit). A non-differentiable decode-time overlay means the loss/eval no longer describe the **deployed decoder** — you'd have to re-validate the *combined* system and calibrate a new interpolation weight, adding eval-validity risk before the loop has even shown it moves. Add only after the loop is proven, and as a *targeted* fix.

## When to Surface

**Trigger:** loop plateaus + motif-reuse failure → add a relative-space stochastic memory / retrieval bias. Separately → pick up the hard-grammar legality mask whenever structural-validity defects appear.

Present during `/gsd-new-milestone` when the milestone scope matches any of:
- "the model ignores / fails to reuse the user's recurring motifs or idiom"
- "generated responses show structural-validity defects" (malformed token grammar, out-of-range durations, overlaps)
- "personalization / per-user memory decoupled from retraining"
- "low-data sample efficiency / exact-recall on a small corpus"
- "constrained / grammar-masked decoding"

## Scope Estimate

**Medium** — a phase or two. The hard-grammar mask alone is small (a phase, possibly less: an FSM over the known vocab grammar + a logit-mask hook). The stochastic/retrieval memory is the larger half (relative-space representation, the memory store, soft interpolation, and re-validating the combined decoder against the eval rubric).

## Breadcrumbs

- `apollo/scripts/generate.py:103–106` — **the exact insertion point.** The per-step logit transform (`next_logit = logits/temperature` → `topk` → `softmax` → `multinomial`). A legality mask multiplies in here; a style-bias distribution interpolates in here, *before* top-k/sampling.
- `apollo/model/transformer.py:103` — model emits `(B, T, vocab_size)` next-token logits; the overlay consumes the final-position slice.
- `apollo/tokenizer/vocab.py`, `apollo/tokenizer/types.py`, `apollo/tokenizer/bins.py` — the vocab/grammar the **authored FSM** would be specified from (4 tokens/note: pitch, velocity, time, duration; VOCAB_SIZE=256 with reserved tail).
- `apollo/tokenizer/decoder.py` / `encoder.py` — where a **relative/interval** view for the stochastic trie would be derived (absolute tokens are the wrong key).
- **Related seeds:**
  - `SEED-006-generative-grammars-phrase-relations.md` — recursive grammar over *phrase relations / musical form* (higher altitude). SEED-010 is the **token-stream, decode-time** sibling: same "symbolic structure over neural fill-in" philosophy, but operating one level down (per-token legality/bias, not phrase-category productions). Consider sequencing them together if a "musical structure" milestone is scoped.
  - `SEED-007-training-sufficiency-diversity-metrics.md` — diversity/sufficiency metrics could detect the "motif-reuse failure" that triggers this seed.

## Notes

Discussed 2026-06-02 during Phase 5 planning. Framing that crystallized the idea: "same substrate, two readouts (probabilities vs membership), two origins (learned vs authored), composable as layers." This is a decoder-side *memory/constraint mechanism*, NOT a model-capability change — it sits beside (not inside) the checkpoint, reinforcing the per-instance, weights-orthogonal artifact framing.

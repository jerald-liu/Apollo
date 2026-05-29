---
id: SEED-006
status: dormant
planted: 2026-05-20
planted_during: v2.0 / Phase 03 (corpus-inference) — after external course review
trigger_when: After v1 ships, or when scoping a milestone focused on musical structure / form
scope: Large
---

# SEED-006: Generative grammars over musical phrase relationships

## Why This Matters

Apollo's current model learns call→response as a *flat* mapping: given this phrase, emit a complementary one. There is no explicit notion of *what kind of relation* the response bears to the call — echo, contrast, continuation, variation, development. These are the building blocks of musical form, and they are inherently **recursive**: a "variation" of a phrase can itself be varied; a "contrast" pair can become a motif that is then contrasted at a higher level.

A generative grammar formalizes this. Non-terminals describe phrase categories (Theme, Variation, Contrast, Cadence, …); production rules describe how one phrase begets another (`Theme → Theme | Variation(Theme) | Contrast(Theme) + Return(Theme)` and so on). Each terminal is a concrete MIDI phrase emitted by Apollo's neural model. The grammar gives structure; the neural model fills it in.

This separates **what kind of thing to say next** (grammar — symbolic, interpretable) from **what the thing actually sounds like** (neural — learned from authored examples). The grammar is what lets phrases recursively compose into themes, themes into passages, passages into pieces.

## Grammars Encapsulate Varying Tokens / Metadata

User's framing: "The grammars may encapsulate varying tokens/metadata."

This means a grammar production isn't just "next phrase is X" — it can carry metadata that constrains the neural generation:
- **Pitch-class set constraints** (this variation stays within the prompt's mode)
- **Register shifts** (contrast is an octave higher)
- **Rhythmic transformations** (augmentation, diminution)
- **Timbral metadata** (this phrase keeps the prompt's preset; that phrase is allowed to vary it)
- **Phrase-class labels** (theme / variation / contrast / cadence — feeds back as a conditioning token)

Critically, the grammar's metadata becomes part of the conditioning signal to Apollo's transformer. The model learns "given prior phrase X and metadata `{class=Variation, register=+0, mode=preserve}`, emit Y." Apollo's vocab already reserves space for metadata tokens — these slot in naturally.

## Where This Composes With Existing Seeds

- **SEED-002 (Hierarchical call-and-response):** SEED-002 nests call/response pairs by treating them as atomic theme-level units. SEED-006 is the *grammar layer that decides which kind of theme follows which* — what SEED-002 makes structurally possible, SEED-006 makes structurally meaningful. Sequence: SEED-002 first (proves the nesting works), then SEED-006 (adds the rules over the nesting).
- **SEED-004 (Bidirectional chaining):** Grammar productions could be direction-aware — "the call that *precedes* this response is of class X." Direction tokens already proposed in SEED-004 become grammar metadata.
- **SEED-005 (Parameter locking):** Grammar metadata is a natural source for default locks. "This production says 'variation in same key' → automatically lock pitch range and unlock rhythm."

## Open Questions

1. **Where does the grammar come from?** Three options:
   - **Hand-authored:** user writes production rules. Most interpretable, least scalable.
   - **Induced from corpus:** user labels each authored pair with a phrase-relation tag (echo, contrast, …); grammar is learned. Aligns with Apollo's active-learning loop.
   - **Discovered:** clustering over the latent space of Apollo's existing model surfaces phrase-relation categories without explicit labels. Most ambitious; weakest interpretability.
2. **Grammar formalism.** CFG? Probabilistic CFG? Tree-adjoining grammar? L-system (well-suited to recursive musical structure)? L-systems and stochastic CFGs are both well-documented for music — pick based on whether recursion or probability is the dominant need.
3. **Where the grammar lives in inference.** Two architectures:
   - **Grammar as outer loop, model as inner:** grammar picks the next non-terminal, model generates one phrase realizing it. Clean separation; grammar fully interpretable.
   - **Grammar tokens woven into the model's vocabulary:** model emits both phrase tokens and structure tokens in one autoregressive stream. Tighter coupling; harder to inspect.
4. **Authoring overhead.** Hand-labeling phrase relations on a 30-pair corpus is fine; on a 300-pair corpus it becomes a chore. Need a labeling UI that scales.

## When to Surface

**Trigger A:** A milestone is scoped that mentions musical form, structure, themes, passages, composition, songwriting, or "recursively built phrases."
**Trigger B:** SEED-002 has shipped and is producing theme-level pairs — the prerequisite for grammar rules to operate on.
**Trigger C:** User explicitly requests rule-based or interpretable control over phrase relations.

Present during `/gsd-new-milestone` when any of the above triggers are met.

## Scope Estimate

**Large** — A full milestone (or two). Requires:
- Decision on grammar formalism (PCFG, L-system, TAG, …)
- Decision on where the grammar comes from (hand-authored vs. induced vs. discovered)
- Vocab extension: phrase-class metadata tokens (use reserved slots)
- Corpus extension: phrase-relation labels per pair (UI or annotation pass)
- Training: condition the existing transformer on grammar metadata
- Inference: grammar driver that picks productions and invokes the neural model per terminal
- Evaluation: structure-aware rubric — "does the response *play the role* the grammar requested?"

## Reference

- **Lesson 9 — Generative grammars** (Valerio Velardo, *Generative Music AI Course*, UPF MTG): https://github.com/musikalkemist/generativemusicaicourse/blob/main/09.%20Generative%20grammars/Slides/9.%20Generative%20grammars.pdf
- **Workshop home:** https://www.upf.edu/web/mtg/generative-music-ai-workshop
- See also [`.planning/EXTERNAL-RESEARCH.md`](../EXTERNAL-RESEARCH.md) — course is conceptually useful but offers no production-grade implementation. Primary literature on L-systems for music and probabilistic CFGs is the better source when this seed surfaces.

## Breadcrumbs

- `apollo/tokenizer/vocab.py` — reserved-slot policy; phrase-class metadata tokens will live here
- `apollo/model/model.py` — ApolloModel's conditioning path; grammar metadata becomes additional conditioning input
- `.planning/seeds/SEED-002-hierarchical-call-and-response.md` — prerequisite for grammar to operate on theme-level units
- `.planning/seeds/SEED-004-bidirectional-chaining.md` — direction tokens compose with grammar metadata
- `.planning/seeds/SEED-005-parameter-locking-ui.md` — grammar metadata is a natural source for default locks
- `.planning/EXTERNAL-RESEARCH.md` — pointer to the Velardo course and its limits

## Notes

The user's framing — "grammars may encapsulate varying tokens/metadata" — is the structurally important insight here. A grammar over plain phrases is just symbolic music theory. A grammar that carries the *conditioning metadata for the neural model* is the bridge: it turns Apollo from a stylistic mimic into a composer that can be reasoned about structurally. That's the actual prize.

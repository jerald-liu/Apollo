# External Research Notes

Findings from outside materials, mapped to Apollo phases. Source-of-truth for "did we already look at X?" so future phases don't re-research.

---

## Generative Music AI Course (Velardo / Sound of AI)

**Source:** https://github.com/musikalkemist/generativemusicaicourse
**Reviewed:** 2026-05-20
**Format:** 22 lessons, mostly PDF slides + YouTube. Code only in L10/12/14/16/19/20/21. Stack is TF/Keras + music21 — not directly portable to Apollo's PyTorch/MPS setup.

**Net assessment:** Validates that Apollo's encoder-decoder + cross-attention architecture is mainstream. Does not solve any of Phase 1-4's hard problems. Useful as a conceptual checkpoint, not a code reference.

### Relevance by Phase

**Phase 1 — Tokenizer & Ingest** *(complete)*
- Course's tokenization (L19: `"C4-1.0"` pitch-duration strings) is **lossy and not adopted**. Apollo's pitch + velocity + time-shift + duration vocab is strictly richer. Course never covers REMI / MIDI-like / compound tokens — known gap, consult REMI (Huang & Yang 2020) and Music Transformer directly if extending.

**Phase 2 — Model & Training** *(complete)*
- L19 (TF encoder-decoder on ~75 nursery rhymes) is a structural sanity check: a from-scratch transformer *does* work on tiny corpora. Apollo's MEL-prefix design already diverges from this — finding does not require rework.
- L17/18 transformer slides: standard conceptual material, nothing new.
- **Gap:** course covers neither mel-spec CNN encoders nor cross-attention vs FiLM vs prefix-tuning tradeoffs. Apollo's MEL prefix choice was made independently and remains uncontested by this source.

**Phase 3 — Corpus & Inference** *(upcoming — findings actionable here)*
- L19's `MelodyGenerator` uses **greedy argmax only**. Apollo needs temperature + nucleus (top-p) / top-k sampling for `generate.py`. Borrow patterns from L21 Compose & Embellish notebook or implement from MusicGen/Music Transformer reference.
- **Action for Phase 3 plan:** explicitly include temperature + nucleus sampling in `generate.py`; do not ship greedy-only.

**Phase 4 — Evaluation Loop** *(upcoming)*
- Course does **not** cover subjective rubric design or held-out evaluation protocols for generative music. No reuse possible. Apollo's 1-5 "call-response fit" rubric stands on its own — primary literature (MusicGen human-eval methodology, MOS protocols) is the better source if this needs hardening.

### Recommendations Not Adopted

- **L11-12 Markov baseline** suggested as a floor for the 30-pair corpus: **deferred.** Apollo's smoke train already hits `type_accuracy=1.0`; a Markov floor would be informative but is not on the critical path. Revisit only if held-out rubric scores stall across two iterations.
- **L20 RAVE / L21 Compose & Embellish notebooks:** worth skimming for sampling code (see Phase 3 above) but not as architectural references — RAVE is a VAE and C&E is two-stage symbolic, neither matches Apollo's mel-prefix + transformer decoder shape.

### Gaps the Course Does Not Cover (look elsewhere)

1. Mel-spectrogram CNN encoders for short audio clips → already solved in Phase 2.
2. Cross-attention vs FiLM vs prefix-tuning conditioning tradeoffs → MEL prefix chosen; not revisiting.
3. Small-corpus overfitting mitigation (dropout schedules, MIDI augmentation, mixup) → **open question for Phase 3** if held-out loss diverges.
4. Subjective evaluation rubrics → open question for Phase 4.
5. MPS / Apple-Silicon training → solved in Phase 2.

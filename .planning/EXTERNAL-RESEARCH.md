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

---

## Magenta (Google Research)

**Source:** https://magenta.tensorflow.org/ + archived GitHub (google/magenta) + active successor projects (Magenta RealTime, Lyria RealTime API)
**Reviewed:** 2026-05-28
**Format:** Research initiative (now largely archived Jan 2026); active successors are cloud-based audio generation APIs. Stack is TF/Keras for legacy models; new work is internal Google infrastructure.

**Net assessment:** Apollo is NOT reinventing critical wheels. The ML plumbing (tokenizer, transformer, mel encoder) is incremental on published Magenta work — correctly so. Apollo's core differentiation is the domain (FM synth + user style) and the product design (active-learning loop as the deliverable). **Do not integrate Magenta. Build standalone.**

### Magenta Model Inventory (relevant to Apollo)

| Model | What it does | Apollo relevance |
|---|---|---|
| **Music Transformer** (Huang et al. 2018) | Self-attention on MIDI tokens, relative pos. encoding, continuation | Apollo's transformer backbone is this architecture. Not reinventing — standing on it. |
| **MusicVAE** | VAE on 4-bar sequences, MAESTRO corpus, interpolation | Not used. Apollo doesn't need latent interpolation; different task. |
| **PerformanceRNN** | LSTM on expressive timing/dynamics (piano) | Same token vocabulary concept; different architecture and corpus. |
| **DDSP** | Differentiable DSP, learns audio synthesis parameters | Phase 3/4 relevance: if mel conditioning generalizes poorly across unseen presets, DDSP-style parameter learning is the upgrade path. |
| **Magenta Studio** | Ableton Live plugins (Continue, Groove, Interpolate, Drumify) | **Groove** is a post-processing candidate for v2 responses (humanized timing/velocity). Not needed v1. |
| **Magenta RealTime / Lyria** | Audio generation conditioned on MusicCoCa embeddings (text+audio); cloud API | Different task (audio out, not MIDI out) and requires cloud. Not applicable v1. |
| **DrumBot / ML-Jam** | Real-time call-and-response (melody → drum response, human-AI trading) | Same concept, different domain. Magenta's version is real-time + cloud; Apollo is offline + local. |

### Is Apollo Reinventing Wheels?

**MIDI tokenization** — Partially parallel, but justified. Magenta uses note-event tokens (pitch, velocity, timing). Apollo's 4-token-per-note scheme covers the same concepts with a cleaner extensibility constraint (reserved vocab ranges for future CC tokens without checkpoint invalidation). Not a critical reinvention.

**Transformer backbone** — NOT reinventing. Apollo correctly builds on Music Transformer (2018). Response-only loss masking is standard seq2seq practice.

**Mel conditioning** — **Novel combination.** Magenta RealTime conditions audio generation on pretrained MusicCoCa embeddings (cloud, expensive). DDSP conditions on learned audio parameters (synthesis-focused). No prior Magenta tool does mel-conditioned MIDI response generation. Apollo's insight — that FM timbre variation demands timbre-aware response — is sound and unaddressed in the literature.

**Active-learning loop** — NOT in Magenta. Magenta ships static trained models; the iteration loop is the user's problem. Apollo makes the loop itself the product. This is the key differentiator.

**Small custom corpus** — NOT in Magenta. Magenta learns broad distributions from millions of examples (MAESTRO, etc.). Apollo learns "your FM style" from 30–200 hand-authored pairs. Genuinely underserved niche.

### Relevance by Phase

**Phase 1 — Tokenizer & Ingest** *(complete)*
- Apollo's tokenizer is equivalent to Magenta's note-event vocabulary. No rework needed.
- If expanding to polyphonic in v2, consult Magenta.js multitrack representation.

**Phase 2 — Model & Training** *(complete)*
- Music Transformer validates Apollo's architecture choice.
- `enable_nested_tensor=False` MPS fix (Phase 2 decision) is Apollo-specific — not covered in Magenta's TF codebase.

**Phase 3 — Corpus & Inference** *(next)*
- Magenta has nothing on FM synth corpus authoring workflows. Apollo is on its own here.
- DDSP is worth revisiting if mel conditioning generalizes poorly to unseen presets: parameter-space conditioning (filter cutoff, LFO rate) may be richer than raw mel for FM timbres.
- Groove-style humanization (Magenta Studio) could layer over `generate.py` output as a v2 post-processing step — not v1 scope.

**Phase 4 — Evaluation Loop** *(complete — rubric + grading UI shipped)*
- Magenta has no precedent for an active-learning evaluation loop as a product feature.
- Magenta Studio's rubric dimensions (note density, rhythmic complexity, melodic contour) could enrich the Phase 4 rubric if held-out scores stall. Reference if needed.

### Reuse Opportunities (Deferred)

| Opportunity | When | Notes |
|---|---|---|
| DDSP parameter conditioning | v2, if mel conditioning doesn't generalize across unseen presets | Research DDSP's audio parameter learning as a richer timbre signal than raw mel. |
| Groove-style humanization | v2 post-processing | Layer timing/velocity variation over generated response MIDI. |
| Polyphonic tokenization (Magenta.js multitrack) | v2 if scope expands past monophonic | Apollo v1 is monophonic by design. |
| Music Transformer positional encoding variants | Only if sequence length grows beyond 64 | Current max_seq_len=64 is well within standard learned pos. emb. range. |
| MOS / human-eval protocol from MusicGen paper | Phase 4 rubric hardening | If held-out scores are questioned, adopt formal MOS methodology as secondary metric. |

### What Magenta Does Not Cover (Apollo owns this)

1. FM synth (Operator) MIDI generation — Magenta is piano-focused or instrument-agnostic.
2. Mel-conditioned MIDI response generation — novel combination not present in Magenta's model inventory.
3. User-style personalization from tiny corpus (30–200 pairs).
4. Active-learning loop as product deliverable with held-out improvement gates.
5. Local-only MPS training with no cloud dependency.

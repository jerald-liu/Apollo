# Apollo

## What This Is

Apollo is a generative call-and-response model for Ableton **Operator** (FM synth). You play a short MIDI phrase routed through an Operator preset; the model returns a complementary MIDI response in your own authored style. The corpus is hand-curated by the user — paired MIDI tracks (call + response) authored in Ableton — and the model learns the user's call→response intuition implicitly.

## Core Value

Given a short MIDI call played through an Operator preset, the model produces a response that *feels like the user* responding to themselves. The active-learning loop (author → train → listen → identify gaps → author more) is the deliverable as much as any single trained model.

## Requirements

### Validated

**Validated in Phase 1 (Tokenizer & Ingest):** Tokenizer round-trips MIDI, mel extractor produces (96,128) tensors, pair discovery + hash split + artifact format, error handling + smoke test.

**Validated in Phase 2 (Model & Training):** MelEncoder (109,184 params, CNN) compresses mel → (B,128) embedding. ApolloModel (976,384 params, causal transformer + MEL prefix). ApolloDataset + collate_fn packs [BOS, call, SEP, response, EOS, PAD]. Masked CE loss (response-only, `>= sep_pos` boundary). Smoke train: `type_accuracy=1.0` on 4 pairs, 1.88s on MPS. Checkpoint round-trips bit-identically (5-key format).

### Active

- [ ] Author ≥30 call/response pairs in Ableton across varying Operator presets
- [ ] Pair folder layout: `data/pairs/NNN/{call.mid, call.wav, response.mid}` (NNN zero-padded)
- [ ] MIDI tokenizer: pitch + velocity + timing + duration, monophonic, quantized-grid time bins, vocab structurally extensible to pitch bend / mod wheel / CCs without breaking checkpoints
- [ ] Mel encoder conditions the model on the call's rendered audio (`call.wav` → mel features → embedding fed alongside MIDI tokens)
- [ ] Training packs `[BOS, call_tokens, SEP, response_tokens, EOS]` with **loss masked to response tokens only**
- [ ] Train from scratch — no warm-start from any prior checkpoint
- [ ] 20% of authored pairs held out, never trained on
- [ ] Inference: `generate.py` accepts a call `.mid` + `.wav`, emits a response `.mid`
- [ ] Listen-test rubric includes a "call-response fit" dimension (1–5), scored by user
- [ ] Active-learning loop tooling: track held-out scores across iterations, surface deltas
- [ ] Ship v1 when two consecutive iteration rounds both improve held-out call-response-fit score

### Out of Scope

- **Pitch bend / mod wheel / CC tokens in v1** — vocab leaves headroom for these, but v1 ships notes-only. Reason: keep first-pass scope small; expression can be added without re-architecture.
- **Real-time Max-for-Live deployment** — v1 is offline `.mid` → `.mid`. Reason: validate the musical bar before the latency bar.
- **Free/humanized timing** — v1 corpus is quantized to grid. Reason: smaller vocab, cleaner training signal; groove enters as a later corpus extension.
- **Polyphonic generation** — v1 is monophonic both sides. Reason: clean tokenization, smaller model, matches authored corpus style.
- **Phrases longer than ~2 sec / >6 notes per side** — v1 stays in the "tiny gesture" regime. Reason: small context window keeps the model small and training local-runnable.
- **Audio output from the model** — response is MIDI only; user picks the response preset in Ableton. Reason: scope explosion; symbolic output is sufficient to validate the call→response idea.
- **Non-Operator instruments** — v1 is Operator-only. Reason: timbre space constrained to one FM synth family makes mel conditioning learnable on a small corpus.
- **Pretraining on MAESTRO or other corpora** — train from scratch. Reason: prior piano-derived priors (pedal-active rate, piano dynamics envelope) actively conflict with FM/Operator material. Prior piano/MAESTRO code lives on the `deprecated` branch for reference only.
- **Relationship-mode labels** (call-back / answer / continuation) — user authors naturally, model learns implicit distribution. Reason: zero labeling overhead; "Jerald-shape" is the target, not any specific mode.

## Context

**Prior work.** A prior milestone (v1.0) trained a transformer on MAESTRO piano. It hit a representation-level dynamics blocker (MAESTRO's 91-95% pedal-active prior was load-bearing in the output distribution). That milestone is deferred. Its codebase lives on the `deprecated` branch as historical reference only — *not* a model lineage. This project is a clean restart (`call-and-response-v1` branch, orphan, three scaffold files).

**Corpus authoring.** The user authors pairs in Ableton: two MIDI tracks, both running Operator (with potentially different presets per pair). Each pair is exported as three files: `call.mid`, `call.wav` (manual bounce/freeze from Ableton, captures timbre context), and `response.mid`. Authoring is the rate-limiting step; everything else exists to make iteration on the corpus cheap.

**Why Operator (FM).** FM has a small, predictable spectral structure compared to piano. Timbre carries information in this corpus — the same call shape feels different through a bright pluck vs. a soft pad, and the right response differs accordingly. Mel-conditioning is the channel through which the model gets timbre context.

**Active-learning is the product.** A single trained model is not the goal. The goal is a methodology: author 30 → train → listen → identify gaps → author 20 more → retrain → confirm scores improved. v1 ships when this loop demonstrably works (two consecutive improvements on held-out scores).

## Constraints

- **Tech stack**: PyTorch transformer + mel encoder (small CNN). Local-runnable on MPS (Apple Silicon) — no Modal/cloud needed for v1 given the tiny model + tiny corpus.
- **Corpus size**: ≥30 pairs to start; comfort zone 100–200 pairs. Pitch-shift ±5 semitones augmentation gives ~11× but interacts with mel conditioning (audio must be shifted or re-rendered to stay aligned — a plan-phase decision).
- **Authoring tool**: Ableton Live with Operator. No CLI/headless render — user manually bounces audio per pair.
- **Latency**: Not a v1 constraint (offline `.mid` → `.mid`). Real-time M4L is a later milestone.
- **Vocab extensibility**: First-version tokenizer must reserve space for pitch bend / mod wheel / CC tokens so adding them later doesn't invalidate existing checkpoints.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Instrument = Operator only | FM has bounded spectral structure; mel-conditioning becomes learnable on a small corpus | — Pending |
| Monophonic, tiny gestures (0.5–1.5s, 2–6 notes) | Smallest viable scope; model stays tiny, training fast, authoring tractable | — Pending |
| Quantized timing first, groove later | Smaller time-bin vocab; iterate corpus complexity after baseline works | — Pending |
| No relationship-mode labels | Zero labeling overhead; user-shape is the implicit target | — Pending |
| Preset varies pair-to-pair + mel-condition the call | Timbre is part of the corpus signal; mel-condition is the channel that carries it | — Pending |
| Response loss only | Model isn't penalized for the call side; learns to generate, not autoencode | — Pending |
| Train from scratch (no MAESTRO pretrain) | Piano priors actively conflict with Operator material; cleaner to start fresh | — Pending |
| Ship criterion = two consecutive held-out-score improvements | Validates the iteration loop, not just a single lucky model | — Pending |
| Vocab is extensible (room for bend/CC tokens) | Adding expression later must not break existing checkpoints | — Pending |
| Manual Ableton bounce for `.wav` | Most natural workflow; no separate synth-render pipeline | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-19 after initialization*

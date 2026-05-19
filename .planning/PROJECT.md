# Apollo

## What This Is

Apollo is a real-time generative music co-performance system for piano and Max for Live. It listens to what a musician plays, generates a musical response in MIDI, and sends it back to Ableton Live via an OSC bridge — fast enough to feel like a live collaborator rather than a render job. The model is a causal transformer trained on MAESTRO, with streaming note-on/note-off tokenization for minimal input latency.

## Core Value

A pianist plays and Apollo responds in real-time — note-for-note, phrase-for-phrase, within 10ms of keypress.

## Requirements

### Validated

- ✓ MAESTRO preprocessing pipeline (MIDI tokenization, mel spectrogram extraction, streaming tokenizer) — Phase 1
- ✓ Autoregressive transformer with KV-cache (11M params, 2.7× speedup over naive decode) — Phase 1
- ✓ v2 augmented training: best val loss 2.1641 (50K steps, pitch augmentation, label smoothing) — Phase 1
- ✓ Streaming note-on/note-off tokenizer (259-token vocab, 2× musical context per window, zero duration-wait latency) — Phase 1
- ✓ OSC inference server with streaming handlers (/apollo/note_on, /apollo/note_off) — Phase 1
- ✓ FluidSynth synthesis pipeline (MIDI → WAV via bundled soundfont) — Phase 1
- ✓ Modal cloud GPU training infrastructure (A100, 12h timeout, config-driven data dir) — Phase 1

### Active

- [ ] v3 mel training run completes (80K steps, MelEncoder CNN conditioning, batch=64)
- [ ] v4 streaming training run completes (80K steps, 259-token vocab, batch=256, torch.compile)
- [ ] v3 checkpoint pulled, WAVs generated at temperatures 0.7/0.9/1.1, audio evaluated
- [ ] v4 checkpoint pulled, WAVs generated, audio evaluated against v2 baseline
- [ ] OSC loopback test: inference_server.py running locally, test script sends note_on/note_off, verifies generated notes return

### Out of Scope

- Live Ableton integration (M4L device wiring) — Phase 2, after training validated
- Multi-scale mel encoder (fine/mid/coarse branches) — Phase 3.2, after single-scale v3 validated
- EnCodec codec decoder (waveform output head) — Phase 4, requires paired audio + new training run
- User personalization embeddings — Phase 2+
- Non-piano instruments / GiantMIDI-Piano data — future milestone

## Context

**Training state:** v3_mel (batch=64, lr=4.2e-4) and v4_streaming (batch=256, lr=6.0e-4, compile=true) are configured and tested locally. Both were stopped mid-run when Modal billing cycle limit was hit. Configs are correct — OOM bugs fixed, VOCAB_SIZE migration complete.

**Blocking issue:** Modal workspace billing limit. Runs need to be re-launched once limit resets or is increased.

**Architecture decisions made:**
- TransformerEncoder (decoder-only) replaced TransformerDecoder — removes 3.4M params of dead cross-attention over zeros
- KV-cache (CausalMHA/CausalTransformerLayer) — O(T) per decode step, 2.7× faster at 50 tokens
- Streaming note-on/note-off split — 3 tokens on keypress (immediate), 2 tokens on release; eliminates duration-wait latency
- MelEncoder: 2-layer Conv2D CNN, AdaptiveAvgPool → d_model, broadcast over token positions
- Pitch augmentation ±6 semitones — 13× effective data, eliminated v2 val plateau at 2.44

**Val loss history:**
| Run | Steps | Best Val | Notes |
|-----|-------|----------|-------|
| base (MIDI only) | 50K | 2.2751 | no augmentation, plateau at step 46K |
| v2 (augmented) | 50K | 2.1641 | pitch aug, label smoothing, TF encoder |
| v3 mel | running | — | mel conditioning, batch 64 |
| v4 streaming | running | — | 259-token vocab, 2× context |

## Constraints

- **Compute**: Modal A100 — 12h timeout per run, ~$3/hr, billing cycle limit applies
- **Latency**: Inference must stay under 10ms/event at ctx=128 on MPS (M4 MacBook)
- **Vocab**: v3 uses 380-token base vocab; v4 uses 259-token streaming vocab — incompatible checkpoints
- **Augmentation**: Pitch/velocity augmentation disabled for v4 streaming (token offset ranges differ from base vocab — needs reimplementation)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| TransformerEncoder over TransformerDecoder | Decoder had dummy cross-attention over zeros (3.4M wasted params) | ✓ Confirmed — no quality regression, 10% faster |
| KV-cache (custom CausalMHA) | O(T²)→O(T) per decode step, essential for real-time | ✓ 2.7× speedup at 50 tokens, ~10× at 512 |
| Streaming note-on/note-off tokenizer | Duration-wait latency (0.5–2s) incompatible with real-time feel | — Pending (v4 training not yet evaluated) |
| Pitch augmentation ±6 semitones | Dataset cycled 89× per run — primary cause of v2 val plateau | ✓ Val improved 0.11 vs base |
| Single A100 over multi-GPU DDP | 11M params use 0.2% VRAM — DDP has sync overhead without benefit at this scale | ✓ Confirmed — throughput bottleneck is batch size, not GPU count |
| batch_size 512 → 64/256 (downscaled) | MelEncoder Conv2D activations OOM at batch=512; compile adds overhead | — Pending (runs not yet complete) |

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
*Last updated: 2026-05-13 after project initialization*

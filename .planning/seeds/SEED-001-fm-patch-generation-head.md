---
id: SEED-001
status: dormant
planted: 2026-05-20
planted_during: v2.0 / Phase 2 (model-training) complete
trigger_when: Phase 4 ship gate reached and v2 milestone scoping begins
scope: large
---

# SEED-001: FM patch generation head — model suggests Operator parameters alongside response MIDI

## Why This Matters

Apollo v1 generates response MIDI but leaves preset selection entirely to the user.
The response's *timbre* is as much a part of call-and-response as its notes — a bright
pluck calls for a different response character than a soft pad. Right now the model
"hears" the call's timbre via mel conditioning but has no channel to express a timbre
opinion in its output.

Adding an FM patch parameter output head closes this loop: the model returns both
**what to play** (MIDI) and **how it should sound** (Operator parameters), giving a
complete call-and-response including sound design. Crucially, this does not require
learning raw waveform synthesis — Operator is DX7/FM4 lineage with a bounded,
interpretable ~150-parameter space. Differentiable FM synthesis libraries (torchsynth,
SynthAX) run 16,000–90,000× faster than realtime and can serve as the training-time
audio renderer, enabling a mel reconstruction loss on the suggested patch without any
cloud dependency.

Reference: https://gist.github.com/0xdevalias/5a06349b376d01b2a76ad27a86b08c1b

## When to Surface

**Trigger:** Phase 4 ship gate reached (two consecutive held-out-score improvements) and
v2 milestone scoping begins.

This seed should be presented during `/gsd-new-milestone` when any of these match:
- Milestone involves extending the output beyond symbolic MIDI
- Milestone involves tighter Ableton / preset integration
- Milestone scope includes sound design automation or timbre modeling
- v2 tag or "patch generation" appears in milestone description

## Scope Estimate

**Large** — full milestone or major phase. Involves:
1. Corpus authoring change: capture Operator patch snapshots (`.fxp` or sysex dump) per pair alongside existing `call.mid / call.wav / response.mid`
2. New model output head: FM parameter prediction branch on top of ApolloModel, trained jointly
3. Differentiable FM renderer: integrate torchsynth or SynthAX as training-time audio backend for reconstruction loss
4. Dexed bridge: map Dexed's open DX7 parameter format ↔ Ableton Operator parameters (structural equivalence, ~155 params)
5. Inference extension: `generate.py` outputs `response.mid` + `response_patch.fxp` (loadable in Dexed / exportable to Operator)
6. Evaluation: listen-test rubric gains a "timbre fit" dimension alongside existing "call-response fit"

## Breadcrumbs

Relevant code and decisions in the current codebase:

- `apollo/model/train.py:155` — `save_checkpoint` writes `model_config` dict: extension point for a `patch_head_config` key with zero breaking changes
- `apollo/model/train.py:173-176` — checkpoint keys: `model_state_dict`, `mel_encoder_state_dict`, `vocab`, `model_config`, `training_meta` — a `patch_head_state_dict` key drops in cleanly
- `apollo/model/transformer.py:62` — `self.mel_enc = MelEncoder(d_model=d_model)` — patch head would sit at the same level, conditioned on the final hidden state
- `apollo/model/mel_encoder.py` — MelEncoder already encodes call timbre into `(B, d_model)` — this embedding is the natural input to the patch prediction head
- `.planning/phases/999.1-fm-patch-generation/` — backlog item registered alongside this seed

## Notes

- **torchsynth** (`pip install torchsynth`) — PyTorch-native modular FM synthesis, GPU-accelerated, differentiable. Ideal for reconstruction loss during training.
- **SynthAX** — JAX-based, 90,000× realtime. Faster but requires JAX; likely overkill given MPS training target.
- **Dexed** — open-source DX7 VST with fully documented parameter format. The bridge between open tooling and Ableton Operator.
- **Sound2Synth** (referenced in gist) — academic work on FM parameter estimation from audio; useful prior art for the loss function and evaluation approach.
- The v1 checkpoint format was deliberately designed with `model_config` as a freeform dict — adding `patch_head_config` requires no migration of existing checkpoints.
- Corpus authoring overhead is the real gate: the user must add a "export patch" step to the Ableton authoring workflow. Worth scoping that UX before committing to the technical architecture.

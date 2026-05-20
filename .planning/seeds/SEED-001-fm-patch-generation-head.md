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
**what to play** (MIDI) and **how it should sound** (Operator parameters).

### Key insight: preset-as-transformation, not inverse synthesis

The naive approach (Genopatch-style) would be: audio → search parameter space to find
a matching preset. That's a hard inverse problem with many-to-one ambiguity.

The Apollo case is fundamentally different: **the call preset is already known** — the
user authored it. The response preset is a *transformation* of the call preset, anchored
to a known starting point. Instead of reverse-engineering parameters from audio, the
model learns: "given this FM preset, what is a musically interesting mutation of it for
the response?"

Examples of valid transformations the model might learn:
- Flip the FM algorithm for timbral contrast
- Change coarse tuning on carriers/modulators to shift harmonic character
- Swap modulator waveform (sine → triangle) for a softer response
- Reduce FM depth on a modulator to thin out a dense call

This is a direct parameter-to-parameter mapping problem, not a reconstruction problem.
The mel conditioning (call.wav) becomes less load-bearing for preset prediction — you
already have the ground truth parameters. The mel remains useful for the MIDI side.

**Training signal:** actual (call_params, response_params) corpus pairs — the parameter
delta is the target, not reconstructed audio. Differentiable FM synthesis libraries
(torchsynth, SynthAX) are no longer required as the primary training mechanism; they
could still serve as an optional augmentation or sanity-check renderer.

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
1. Corpus authoring change: export `call_preset.adg` and `response_preset.adg` per pair alongside existing `call.mid / call.wav / response.mid` — adds one export step per pair in Ableton
2. Preset parser: read Ableton `.adg` (XML) → flat parameter vector; define the Operator parameter schema (~40–60 meaningful params: algorithm, carrier/modulator coarse/fine, FM depth, envelope shapes, filter, LFO)
3. New model output head: parameter-delta prediction MLP on top of ApolloModel's final hidden state, trained to predict response_params given call_params + call context
4. Training signal: (call_params, response_params) pairs from corpus — supervised regression on parameter delta, no audio reconstruction loss required
5. Inference extension: `generate.py` outputs `response.mid` + `response_preset.adg` (directly loadable in Ableton Operator)
6. Evaluation: listen-test rubric gains a "timbre fit" dimension alongside existing "call-response fit"

Note: torchsynth/SynthAX differentiable FM rendering is no longer the primary training mechanism — direct parameter supervision is cleaner. Could still be used as optional augmentation to generate synthetic (params, audio) training pairs if the real corpus is too small for the preset head.

## Breadcrumbs

Relevant code and decisions in the current codebase:

- `apollo/model/train.py:155` — `save_checkpoint` writes `model_config` dict: extension point for a `patch_head_config` key with zero breaking changes
- `apollo/model/train.py:173-176` — checkpoint keys: `model_state_dict`, `mel_encoder_state_dict`, `vocab`, `model_config`, `training_meta` — a `patch_head_state_dict` key drops in cleanly
- `apollo/model/transformer.py:62` — `self.mel_enc = MelEncoder(d_model=d_model)` — patch head would sit at the same level, conditioned on the final hidden state
- `apollo/model/mel_encoder.py` — MelEncoder already encodes call timbre into `(B, d_model)` — this embedding is the natural input to the patch prediction head
- `.planning/phases/999.1-fm-patch-generation/` — backlog item registered alongside this seed

## Notes

- **Ableton `.adg` format** — XML; Operator preset parameters are human-readable and parseable without a VST host. The preset-capture step is just File → Save Preset in Ableton, one per track.
- **Parameter schema TBD** — Operator has ~150 raw parameters but many are redundant or irrelevant for timbral identity. The meaningful subset (algorithm, coarse/fine per operator, FM depth, envelope ADSR, filter cutoff/res, LFO rate/depth) is probably 40–60 values. Defining this schema is a prerequisite planning task.
- **Transformation vs absolute prediction** — the model could predict absolute response parameters OR a delta from call parameters. Delta is more natural (the response is a mutation, not an independent patch) and keeps the output space smaller.
- **Corpus authoring overhead** — the real gate. User must add "export preset" to the Ableton workflow per pair. Worth scoping that UX friction before committing to the architecture.
- **torchsynth / SynthAX** — still useful if the real corpus is too small for the preset head; can generate synthetic (params, audio) pairs to pretrain. Not the primary training mechanism under the new framing.
- **Sound2Synth** (referenced in gist) — academic prior art on FM parameter estimation; useful for evaluation methodology even if the training approach differs.
- The v1 checkpoint format was deliberately designed with `model_config` as a freeform dict — adding `patch_head_config` requires no migration of existing checkpoints.

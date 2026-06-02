---
id: SEED-009
status: dormant
planted: 2026-06-02
planted_during: v2.0 / synth-independence decision (Operator → owned Python FM family)
trigger_when: The 3-op v1 timbre space proves too limiting for call-response fit, OR v1 ships and a richer timbre space is scoped
scope: large
---

# SEED-009: Full-topology FM engine (4-op / 11-algorithm / filter / LFO)

## Why This Matters

v1 deliberately ships a **3-operator** FM engine with a small hand-authored param set
(see [[synth-independence-decision]]) because a low-dimensional timbre space is easier for a
small mel encoder to learn from ~30 pairs. That's the right *starting* bet — but it caps the
timbral range a call/response pair can express. If held-out call-response-fit plateaus because
the timbre space is too thin, or if v1 ships and we want richer sound design, the engine should
grow to match Operator's **topology** (not its sound).

## What This Is

Expand the owned Faust FM engine to Operator-class topology:
- **4 operators** (up from 3)
- **11 algorithms** (Operator's routing set; Faust `synths.lib` `dx.algorithm(n)` gives DX7's
  32 as strong prior art to crib the wiring style from)
- **6-param envelopes** (3 rate / 3 level) with loop modes + adjustable slopes
- **Multimode filter** + filter envelope
- **LFO** (audio-rate, multi-destination)
- Multiple oscillator waveforms (beyond sine); optionally additive/user partials

## Explicit non-goal: fidelity

This seed is about **capability/topology, not cloning Operator's sound**. Matching Operator's
exact envelope curves, phase-mod details, and (deliberately imperfect) anti-aliasing is
open-ended and reintroduces the Ableton dependency as ground truth — and Operator's character
was judged incidental. Build a rich FM synth we own; do not chase a clone.

## Dependencies / Interactions

- Must extend the **single source-of-truth FM spec** shared by the Python (corpus) renderer and
  the Phase 5 browser synth — both renderers grow together to stay train/serve consistent.
- Higher-dimensional conditioning: revisit mel encoder capacity and corpus size when triggered.
- Relates to [[SEED-001]] (FM patch generation head) — a richer param schema is more to predict.

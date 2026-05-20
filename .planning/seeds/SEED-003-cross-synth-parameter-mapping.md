---
id: SEED-003
status: dormant
planted: 2026-05-19
planted_during: v2.0 / Phase 03 (corpus-inference)
trigger_when: After 999.1 (FM patch generation head) ships and the Operator parameter schema is validated
scope: Large
---

# SEED-003: Cross-synth parameter mapping — extend Apollo's preset head beyond Operator

## Why This Matters

Apollo v1 is Operator-only. The preset-as-transformation approach (SEED-001 / Backlog 999.1)
learns to mutate Operator parameters in response to a call. But the user's instrument palette
is not limited to Operator — Ableton ships Analog, Wavetable, Drift, and others; third-party
VSTs (Serum, Massive, Diva, etc.) cover the rest.

Extending Apollo's preset head to other instruments means: play a call through any synth, get
back a response MIDI *and* a response preset for that same synth (or a complementary one).
The musical value scales with the breadth of instruments supported.

This is potentially a new field. Synplant/Genopatch works within a single prescribed FM engine.
No existing system handles arbitrary synth plugin parameter mapping at the cross-instrument
semantic level.

## The Two-Level Approach

### Level 1 — Manual ontology mapping (tractable first step)

Research each instrument's manual. Identify structural analogs to Operator's parameter schema:

| Timbral concept | Operator | Analog | Wavetable | Drift |
|---|---|---|---|---|
| Oscillator pitch | Operator coarse/fine | Osc tune/semi | Osc transpose/detune | Osc tune |
| Oscillator shape | Operator waveform | Osc wave | Wavetable position | Osc wave |
| FM/mod depth | Operator FM depth | — (N/A) | Mod matrix amount | — |
| Amplitude envelope | Operator ADSR | Amp ADSR | Amp ADSR | Amp ADSR |
| Filter cutoff | Filter frequency | Filter freq | Filter freq | Filter freq |
| LFO rate/depth | LFO rate/amount | LFO rate/amount | LFO rate/amount | LFO rate/amount |

Define a mapping table per instrument. The preset head then translates the learned
Operator-space transformation into the target instrument's parameter dialect.
Imperfect where capabilities differ (e.g. Analog has no FM; Wavetable has no operators)
but useful wherever structural analogs exist.

### Level 2 — Learned cross-synth embedding (longer-term, novel)

Use audio as the bridge. If Operator patch X and Wavetable patch Y produce perceptually
similar mel spectrograms, they occupy the same region of a shared timbral embedding space.
Train a universal encoder: mel spectrogram → timbral embedding. Each instrument gets its
own inverse head: timbral embedding → instrument-specific parameters.

At inference: call mel → timbral embedding → (Operator head) or (Analog head) or
(Wavetable head) — whichever instrument the user is working with. The model speaks
"timbral language"; each instrument head speaks its own parameter dialect.

This is where it becomes genuinely novel research. The mel encoder Apollo already trains
is the natural starting point for the universal timbral encoder.

## Instrument Priority (native Ableton first)

1. **Analog** — classic subtractive, 2 oscillators + sub, 2 filters; closest to Operator's
   envelope/filter/LFO structure; FM absent but otherwise high parameter overlap
2. **Wavetable** — wavetable oscillators with modulation matrix; different oscillator
   paradigm but identical envelope/filter/LFO skeleton
3. **Drift** — semi-modular analog-style; similar to Analog, adds patch-point routing
4. Third-party VSTs (Serum, Massive, Diva) — after native instruments are validated;
   requires plugin parameter API access (VST3 parameter IDs or Max4Live parameter dump)

## When to Surface

**Trigger:** After 999.1 (FM patch generation head) ships — the Operator parameter schema,
the parameter-delta MLP architecture, and the `.adg` corpus capture workflow must all
exist and be validated before extending to new instruments.

This seed should be presented during `/gsd-new-milestone` when:
- Milestone scope mentions multi-instrument, synth-agnostic, or plugin support
- Milestone mentions Wavetable, Analog, Serum, or any non-Operator instrument
- 999.1 is listed as complete in the roadmap

## Scope Estimate

**Large** — a full milestone, likely split into sub-phases per instrument family:
- Sub-phase A: Define universal timbral ontology + Operator→Analog manual mapping
- Sub-phase B: Analog preset head (parameter-delta MLP, same architecture as 999.1)
- Sub-phase C: Wavetable preset head + corpus authoring for Wavetable pairs
- Sub-phase D: (Optional) Learned cross-synth embedding — shared mel encoder fine-tuning

## Breadcrumbs

- `.planning/seeds/SEED-001-fm-patch-generation-head.md` — prerequisite; defines Operator
  parameter schema, `.adg` corpus capture, and parameter-delta MLP architecture
- `.planning/ROADMAP.md` — Backlog 999.1 (FM patch head), Backlog 999.3 (this item)
- `apollo/model/mel_encoder.py` — MelEncoder; the natural starting point for the universal
  timbral encoder at Level 2
- `apollo/model/transformer.py` — ApolloModel; instrument-specific preset heads would sit
  at the same level as the existing patch head

## Notes

- The manual-mapping approach (Level 1) has a known limitation: where instruments lack
  capability analogs (Analog has no FM depth), the mapping is silent/zero rather than
  semantically equivalent. Document gaps explicitly rather than approximating.
- The learned cross-synth approach (Level 2) requires a large paired dataset of
  (mel, params) examples per instrument — synthetic generation via torchsynth variants
  or plugin parameter sweeps. This is the research contribution.
- VST parameter access outside Ableton: VST3 exposes parameter IDs programmatically;
  a Max4Live device can dump and load parameter states for any instrument in Live.
  The corpus capture workflow for non-native instruments likely runs through M4L.
- "Universal inverse synthesis applicable to all synth plugins" is the long-form research
  statement. Worth tracking whether academic work emerges in this space after 2025.

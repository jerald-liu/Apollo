---
title: Synth-independence decision — replace Ableton/Operator with an owned Python FM family
date: 2026-06-02
context: Explore session following Operator-replacement research + spikes 001/002
status: decided
---

# Synth-Independence Decision

## Decision

Drop Ableton/Operator from Apollo's pipeline. Define the v1 timbre space with an **owned
FM synth family rendered headlessly in Python** (DawDreamer + Faust), starting at
**3 operators**. Per-pair timbre is **hand-authored as FM parameters** (JSON/code), not
dialed by ear in a synth UI. The full 4-op / 11-algorithm / filter / LFO build is deferred
(see [[SEED-009-operator-fidelity-fm-engine]]).

## Why (rationale)

1. **Operator's specific sound is incidental, not load-bearing.** In the explore session
   the call was explicit: we needed *an* FM synth to define a learnable timbre space, not
   Operator's exact character. If the model responds beautifully to a different FM family we
   fully control, that's the same project — not a compromise.
2. **The constraint favors a small timbre space.** REQUIREMENTS.md (Out of Scope: "Non-Operator
   instruments") already bets on "one FM family so mel-conditioning is **learnable on a small
   corpus**." More operators/algorithms = higher-dimensional conditioning = harder for a small
   mel encoder on ~30 pairs. 3-op is deliberately minimal.
3. **No sunk corpus.** `data/pairs/` has only `CORPUS-CONVENTIONS.md` — no authored pairs yet,
   so switching synths invalidates nothing.
4. **Topology is cheap; fidelity is the expensive trap.** Adding operators/algorithms/filter
   is bounded Faust work (~1.5–3× the 3-op DSP). *Matching Operator's sound* (envelope curves,
   phase-mod details, deliberate anti-aliasing per Robert Henke, waveform spectra) is
   open-ended reverse-engineering AND reintroduces the Ableton dependency as ground truth.
   Since Operator's character is incidental, fidelity buys nothing — so we never chase it.

## Spike evidence (validated)

- **Spike 001** (`.planning/spikes/001-dawdreamer-fm-render`): `dawdreamer==0.8.3` installs from
  a prebuilt arm64/Py3.11 wheel in ~5s (no toolchain/Docker); renders MIDI→`call.wav` through a
  Faust FM patch **bit-deterministically**; timbre tracks FM params. No Ableton.
- **Spike 002** (`.planning/spikes/002-fm-mel-conditioning`): the FM audio flows through Apollo's
  **production** `MelExtractor` untouched → exact `(96,128)` COND-01 tensor, deterministic,
  timbre-discriminable (cos 0.85 across-preset vs 1.00 within). Drop-in source swap.
- Packaged as the `spike-findings-apollo` skill.

## Open conflicts to reconcile (do not leave silent)

1. **Phase 5 already specs a no-Ableton FM synth — in the browser.** ROADMAP Phase 5 Success
   Criterion #4 builds an Operator-style **4-operator** Web Audio synth that renders `call.wav`
   locally for the demo app. This decision adds a **Python/Faust headless** renderer for the
   training corpus. Two renderers on two surfaces (browser JS vs Python) → they **must produce
   matching audio** or training data and the app's call rendering diverge (train/serve gap).
   **Implication:** there should be a single source-of-truth FM **spec** (param schema +
   algorithm set + envelope semantics) that both renderers implement; the two engines are
   validated against each other. Reconcile the **3-op (this decision) vs 4-op (Phase 5)** scope.
2. **DATA-01 / DATA-02 wording is now stale.** They say "author/export in Ableton with both
   tracks running Operator" and "`call.wav` (manual Ableton bounce)". These premises are
   superseded by DATA-06. Amend when the rendering phase is planned.
3. **PROJECT.md / CLAUDE.md / `corpus_direction.md` memory** still describe Ableton+Operator
   manual bounce as the authoring model. Update to the owned-FM-family direction.

## Crystallized artifacts from this session

- This note (decision record)
- [[SEED-009-operator-fidelity-fm-engine]] — deferred full-topology build
- REQUIREMENTS.md **DATA-06** — deterministic no-Ableton rendering requirement
- New ROADMAP phase — *Synth-Independent Corpus Rendering* (placement pending Phase 5
  reconciliation above)

# Spike Wrap-Up Summary

**Date:** 2026-06-02
**Spikes processed:** 2
**Feature areas:** Synth-independent rendering
**Skill output:** `./.claude/skills/spike-findings-apollo/`

## Included Spikes
| # | Name | Verdict | Feature Area |
|---|------|---------|--------------|
| 001 | dawdreamer-fm-render | VALIDATED ✓ | Synth-independent rendering |
| 002 | fm-mel-conditioning | VALIDATED ✓ | Synth-independent rendering |

## Excluded Spikes
| # | Name | Reason |
|---|------|--------|
| — | — | none |

## Key Findings
- **Option 1 (headless Python renderer) is feasible end to end.** `dawdreamer==0.8.3`
  installs from a prebuilt arm64/Py3.11 wheel in ~5s (no toolchain/Docker) and renders a
  MIDI phrase through a Faust 2-op FM patch to a **bit-deterministic** `call.wav` — no
  Ableton.
- **Drop-in conditioning.** Apollo's production `MelExtractor` (COND-01) consumes the FM
  audio untouched → exact `(96,128)` log-mel, deterministic, timbre-discriminable
  (cos 0.85 across-preset vs 1.00 within; L2 783; ~2.9 mean-log-mel gap).
- **The blocker is a product decision, not a technical one:** reimplement Operator's
  4-op/11-algorithm topology in Faust for sound identity, vs. adopt a controllable FM family
  as the v1 timbre space (which REQUIREMENTS.md already contemplates).
- **Build gotchas:** poly Faust params need `set_parameter(int_index, …)` not path strings;
  output clips >1.0 (add headroom/normalization before PCM); benign `undefined symbol:
  effect` warning; no `dawdreamer.__version__`. Train/serve must share the same renderer.

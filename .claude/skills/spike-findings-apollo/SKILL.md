---
name: spike-findings-apollo
description: Validated patterns, constraints, and gotchas from spike experiments on replacing Ableton/Operator with a headless Python renderer. Auto-loaded during implementation work on Apollo's audio-conditioning / corpus-rendering pipeline.
---

<context>
## Project: Apollo

Replace manual Ableton/Operator `call.wav` bounces in Apollo's training pipeline with a
headless, scriptable, pure-Python renderer (research option 1). Validate that DawDreamer's
built-in Faust FM engine renders MIDI → audio deterministically with no Ableton, and that
the resulting mel spectrogram is a usable timbre-conditioning signal for the model.

Spike session wrapped: 2026-06-02
</context>

<findings_index>
## Feature Areas

| Area | Reference | Key Finding |
|------|-----------|-------------|
| Synth-independent rendering | references/synth-independent-rendering.md | DawDreamer+Faust FM renders MIDI→`call.wav` deterministically with no Ableton, and the audio drops straight into Apollo's existing `MelExtractor` (96,128) contract with timbre-discriminable mels. Remaining question is product (reimplement Operator vs adopt FM family), not technical. |

## Source Files

Original spike source files are preserved in `sources/` for complete reference:
- `sources/001-dawdreamer-fm-render/` — render_fm.py + README (the renderer)
- `sources/002-fm-mel-conditioning/` — mel_check.py + README (the mel contract check)
</findings_index>

<metadata>
## Processed Spikes

- 001-dawdreamer-fm-render
- 002-fm-mel-conditioning
</metadata>

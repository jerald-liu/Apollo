# Spike Manifest

## Idea

Replace manual Ableton/Operator `call.wav` bounces in Apollo's training pipeline with a
headless, scriptable, pure-Python renderer (research option 1). Validate that DawDreamer's
built-in Faust FM engine can render MIDI → audio deterministically with no Ableton, and that
the resulting mel spectrogram is a usable timbre-conditioning signal for the model.

## Spikes

| # | Name | Validates | Verdict | Tags |
|---|------|-----------|---------|------|
| 001 | dawdreamer-fm-render | DawDreamer + Faust FM renders MIDI→call.wav deterministically on arm64, timbre tracks FM params, no Ableton | VALIDATED ✓ | dawdreamer, faust, fm-synth, rendering, no-ableton |
| 002 | fm-mel-conditioning | Real MelExtractor (COND-01) on FM audio → exact (96,128) contract, deterministic, timbre-discriminable | VALIDATED ✓ | mel, cond, conditioning, torchaudio, timbre |

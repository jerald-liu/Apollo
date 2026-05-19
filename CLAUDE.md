# Apollo — Project Guide

## What This Is

Real-time generative piano co-performance system for Max for Live. The model listens to what a musician plays and generates a musical response in MIDI via OSC, targeting <10ms latency per event.

## Current Milestone

**Ship v3 + v4 Training** — get both runs to completion, evaluate audio quality, verify streaming OSC inference.

See `.planning/ROADMAP.md` for phases and success criteria.
See `.planning/PROJECT.md` for full project context and key decisions.

## Project Structure

```
src/                  Model, inference server, representations
  model.py            ApolloModel with KV-cache (CausalMHA/CausalTransformer)
  inference_server.py OSC bridge for M4L — streaming + legacy handlers
  representation.py   Base 380-token MIDI tokenizer
  streaming_representation.py  259-token note-on/note-off tokenizer
  spectral.py         5-scalar timbral feature extraction (legacy)
scripts/
  train.py            Training loop (DDP, AMP, KV-cache-aware)
  preprocess.py       MAESTRO tokenization (base, mel, streaming modes)
  generate.py         Autoregressive generation + FluidSynth audio
  synthesize.py       MIDI → WAV via FluidSynth CLI
configs/
  v2.yaml             Base augmented config (current best: val 2.1641)
  v3_mel.yaml         Mel conditioning (batch=64, lr=4.2e-4)
  v4_streaming.yaml   Streaming vocab (batch=256, lr=6.0e-4, compile=true)
data/processed/       Base + mel token arrays (MAESTRO 1276 files)
data/processed_streaming/  Streaming 259-token arrays
models/               Local checkpoints (checkpoint_v2_best.pt etc.)
```

## Key Commands

```bash
# Training
make modal-train CONFIG=configs/v3_mel.yaml
make modal-train CONFIG=configs/v4_streaming.yaml

# Pull checkpoints after training
make pull-checkpoints

# Generate audio from checkpoint
venv/bin/python3 scripts/generate.py --checkpoint models/checkpoint_v3_best.pt --audio --temperatures 0.7 0.9 1.1

# Start inference server
venv/bin/python3 src/inference_server.py --config configs/inference.yaml

# Check running Modal jobs
venv/bin/modal app list
```

## GSD Workflow

This project uses GSD for structured planning. Use:
- `/gsd-progress` — check where you are
- `/gsd-plan-phase 1` — plan Phase 1 (Training)
- `/gsd-execute-phase 1` — execute Phase 1 plans

## Important State

- **Modal billing**: Hit cycle limit — runs are paused. Resolve before Phase 1 can proceed.
- **v4 streaming**: Pitch/velocity augmentation is disabled (token offset mismatch — needs reimplementation).
- **Checkpoints on Modal volume**: `checkpoint_step_50000.pt` is the v2 best (2.1641). Saved as `checkpoint_v2_best.pt` locally.

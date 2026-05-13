# Apollo — Project Status Report
**Date:** 2026-05-13

## Phase 0: Research & PoC — COMPLETE

### Deliverables Done
1. **Dataset Audit** (`docs/maestro_audit.json`)
   - MAESTRO v3: 1,276 files, 198.7 hours, full velocity range (1-126), full 88-key coverage
   - Median IOI: 58ms → Apollo must infer under this
   - Pedal used 60% of time → must be in representation
   - Key finding: 10th percentile IOI is ~4ms (chords), real sequential target is <20ms

2. **Latency Benchmark** (`docs/latency_benchmark.json`)
   - All tested architectures viable on Apple Silicon MPS at ctx=128
   - Sweet spot: **Transformer 4L/256d** → 3.9ms median, 4.6M params
   - Even 6L/384d (14.8M params) stays under 10ms
   - CompoundEvent variant: 4.4ms, outputs all fields in one pass

3. **Event Representation** (`docs/representation.md`, `src/representation.py`)
   - Vocab: 380 tokens (time_shift×100, pitch×128, velocity×32, duration×64, pedal×4, timbre×48, specials×4)
   - 5 tokens per event (time_shift, pitch, velocity, duration, pedal)
   - Continuous side-channel: 21 dims (5 note-level spectral + 16 trajectory)
   - No hardcoded Western harmony — harmonic patterns are learned

4. **PoC Model Trained** (`models/apollo_poc.pt`)
   - 4.5M param Transformer, trained on 100 MAESTRO files, 20 epochs
   - Final val loss: ~4.04
   - Generates coherent note sequences from prompts at 3 temperature settings
   - MIDI outputs in `data/processed/apollo_poc_*.mid`

5. **Spectral Pipeline** (`src/spectral.py`, `models/apollo_spectral.pt`)
   - SpectralAnalyzer: extracts centroid, flux, rolloff, flatness, bandwidth, RMS, onset strength
   - NoteSpectralProfile: per-note aggregated timbral descriptors
   - SpectralTrajectory: phrase-level timbral arcs (smoothed over 2s windows)
   - Spectral-aware model trained: 4.7M params, token loss 3.41, timbre MSE 0.048

## Phase 1: Scale Up — IN PROGRESS (training active)

### Done
- **Full MAESTRO preprocessing** (`data/processed/` + Modal `apollo-data` volume)
  - All 1,276 files tokenized (zero errors, 60s on Modal CPU)
  - Train: 35,886 windows × 512 tokens (962 files, 9.45M tokens)
  - Validation: 4,902 windows (137 files, 1.30M tokens)
  - Test: 6,351 windows (177 files, 1.68M tokens)
  - Saved as memory-mapped .npy for fast loading

- **Training infrastructure** (`Dockerfile`, `modal_train.py`, `Makefile`)
  - `Dockerfile` — CUDA 12.1 + PyTorch 2.3 image, code-only (data/checkpoints mounted)
  - `modal_train.py` — Modal IaC: persistent volumes, preprocess + train functions
  - `Makefile` — `make smoke / modal-preprocess / modal-train / pull-checkpoints`
  - `configs/smoke.yaml` — local MPS correctness check (validated: loss 6.04→3.94, 200 steps)
  - `configs/base.yaml` — 6L/384d, 14.8M params, 50K steps
  - `configs/large.yaml` — 8L/512d, ~50M params, 100K steps
  - `scripts/generate.py` — generation + evaluation script for post-training analysis

- **MPS bug fixed**: `fused` AdamW kwarg and `pin_memory` both CUDA-gated — confirmed clean

- **A100 training run ACTIVE** (Modal `ap-tjjeenMpIwH5VGcyIq1x7L`)
  - Started: 2026-05-13
  - At step ~10,000: train loss 1.96, val loss 2.27 — healthy descent, no overfitting
  - Speed: ~530K tok/s on A100 (vs 165K on MPS)
  - ETA: ~5–6 hours remaining

### Not Done Yet
- **Spectral preprocessing**: Full MAESTRO audio (~101GB) not downloaded. Current data is
  MIDI-only — timbre head disabled during this run. Phase 2 target.
- **GiantMIDI-Piano**: 10K+ additional piano files (CC BY 4.0) — planned for next training run
- **Evaluate trained model**: `make pull-checkpoints` then `python scripts/generate.py`

## File Tree (key files)

```
apollo/
├── Dockerfile                 # CUDA 12.1 + PyTorch 2.3 training image
├── Makefile                   # smoke / modal-preprocess / modal-train / pull-checkpoints
├── modal_train.py             # Modal IaC — persistent volumes, preprocess + train
├── requirements.txt           # Dev deps
├── requirements-gpu.txt       # Pinned GPU training deps (used by Dockerfile + Modal)
├── configs/
│   ├── base.yaml              # 6L/384d, 50K steps (active training run)
│   ├── large.yaml             # 8L/512d, ~50M params
│   └── smoke.yaml             # Local MPS correctness check (2L/128d, 200 steps)
├── data/
│   ├── processed/             # Local + Modal apollo-data volume
│   │   ├── train_tokens.npy   # 35,886 × 513, int32
│   │   ├── validation_tokens.npy
│   │   ├── test_tokens.npy
│   │   └── meta.json
│   └── raw/
│       └── maestro-v3.0.0/    # MIDI files
├── docs/
│   ├── architecture.html      # System architecture + workload flow diagrams
│   ├── maestro_audit.json
│   ├── latency_benchmark.json
│   ├── representation.md
│   └── STATUS.md
├── models/                    # Local checkpoints (pull with make pull-checkpoints)
├── scripts/
│   ├── preprocess.py          # MIDI + audio → .npy pipeline
│   ├── train.py               # GPU training (DDP, AMP, cosine LR, checkpointing)
│   ├── generate.py            # Generation + evaluation (post-training)
│   └── run_training.sh        # Legacy one-shot pipeline
├── src/
│   ├── model.py               # ApolloModel (Transformer + spectral encoder + timbre head)
│   ├── representation.py      # Event tokenization + continuous features
│   ├── spectral.py            # FFT analysis pipeline
│   └── inference_server.py    # OSC bridge for M4L real-time inference
└── m4l/                       # Max For Live device
    ├── patchers/apollo_engine.maxpat
    └── code/                  # JS modules (bridge, status, timbre meters)
```

## Next Steps (Priority Order)

1. **Wait for training to complete** — A100 run active, ~5-6 hours remaining
2. **Evaluate**: `make pull-checkpoints && python scripts/generate.py --checkpoint models/checkpoint_best.pt`
   - Listen to generated MIDI, check musical coherence
   - Run `--eval` mode for aggregate stats across 16 samples
3. **If generations are good**: proceed to Phase 2 real-time inference engine
   - Wire M4L device to inference_server.py
   - Validate <20ms latency end-to-end
4. **Next training run**: add GiantMIDI-Piano (10K files), re-run with `--spectral` once audio downloaded

## Architectural Direction (Phase 3–5)

Decisions made 2026-05-13 — not yet implemented:
- **Multi-scale audio encoder**: mel+CQT at fine/mid/coarse temporal granularity replaces hand-crafted 5-scalar spectral features
- **Dual-channel I/O**: audio (always) + MIDI (optional) in; waveform + CC out
- **Soft pitch head**: on-the-fly continuous pitch salience when MIDI unavailable — avoids 12-TET quantization bias
- **Waveform output**: neural codec decoder (DAC/EnCodec) replaces MIDI-only output
- See `docs/architecture.html` for full diagrams

## Cost
- GPU compute: ~$5-15 for current A100 run (Modal)
- Data: $0 (MAESTRO is free)

# Apollo — Project Status Report
**Date:** 2026-04-02

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

## Phase 1: Scale Up — IN PROGRESS

### Done
- **Full MAESTRO preprocessing** (`data/processed/`)
  - All 1,276 files tokenized (zero errors)
  - Train: 35,886 windows × 512 tokens (962 files, 9.45M tokens)
  - Validation: 4,902 windows (137 files, 1.30M tokens)
  - Test: 6,351 windows (177 files, 1.68M tokens)
  - Saved as memory-mapped .npy for fast loading

- **GPU training infrastructure** (`scripts/`)
  - `scripts/preprocess.py` — multiprocessing MIDI→token pipeline, supports spectral
  - `scripts/train.py` — full training script with DDP, AMP, cosine LR, checkpointing, wandb
  - `scripts/setup_gpu.sh` — cloud instance setup
  - `scripts/run_training.sh` — one-command download→preprocess→train pipeline
  - `configs/base.yaml` — 6L/384d, 14.8M params, 50K steps
  - `configs/large.yaml` — 8L/512d, ~50M params, 100K steps

### Not Done Yet
- **Fix minor bug**: `train.py` was running on CPU instead of MPS locally — fixed `fused` kwarg and `pin_memory`, but haven't verified the fix runs clean
- **Spectral preprocessing at scale**: Full MAESTRO with audio (~101GB download) not yet done. Current preprocessed data is MIDI-only (no spectral features). Need to either:
  - Download full MAESTRO (audio) and preprocess locally (slow, ~hours)
  - Or do it on the GPU instance (recommended — faster I/O)
- **Actual GPU training run**: Scripts are ready but haven't been executed on cloud GPU yet
- **GiantMIDI-Piano**: Not downloaded yet (10K+ additional piano files, CC BY 4.0). Good for more training data.

## File Tree (key files)

```
~/Projects/apollo/
├── configs/
│   ├── base.yaml              # 6L/384d, 50K steps
│   └── large.yaml             # 8L/512d, 100K steps
├── data/
│   ├── processed/
│   │   ├── train_tokens.npy   # 70MB, 35K windows
│   │   ├── validation_tokens.npy
│   │   ├── test_tokens.npy
│   │   └── meta.json
│   └── raw/
│       └── maestro-v3.0.0/    # MIDI files
├── docs/
│   ├── maestro_audit.json
│   ├── latency_benchmark.json
│   ├── representation.md
│   └── STATUS.md              # ← this file
├── models/
│   ├── apollo_poc.pt          # PoC checkpoint
│   └── apollo_spectral.pt     # Spectral-aware checkpoint
├── notebooks/
│   ├── 00_dataset_audit.ipynb
│   ├── 01_latency_benchmark.ipynb
│   └── 02_poc_generation.ipynb
├── scripts/
│   ├── preprocess.py
│   ├── train.py
│   ├── setup_gpu.sh
│   └── run_training.sh
├── src/
│   ├── model.py               # ApolloModel (spectral-aware Transformer)
│   ├── representation.py      # Event tokenization + continuous features
│   └── spectral.py            # FFT analysis pipeline
├── requirements.txt
└── .gitignore
```

## Next Steps (Priority Order)

1. **Verify `train.py` runs locally on MPS** (5 min) — just run 50 steps to confirm fixes work
2. **Git commit everything** — repo is not yet committed
3. **Push to cloud GPU and run `base.yaml` training** (~$5-15, 6-8 hours on A100)
   - Upload preprocessed data (92MB) or let the script download + preprocess on GPU
   - For spectral: download full MAESTRO audio on the GPU instance
4. **Evaluate trained model** — generate samples, compare to PoC
5. **Then**: Phase 2 (real-time inference engine) or Phase 3 (user embeddings)

## Cost So Far
- GPU compute: $0 (all local on Apple Silicon)
- Data: $0 (MAESTRO is free)
- Estimated next spend: $5-15 for one A100 training run (6-8 hours at ~$1-2/hr)

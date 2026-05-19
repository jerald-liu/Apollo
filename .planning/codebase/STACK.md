# Technology Stack

**Analysis Date:** 2026-05-13

## Languages

**Primary:**
- Python 3.11 — all model code, training pipeline, inference server, preprocessing
- JavaScript (Node for Max) — Max for Live bridge script (`m4l/code/*.js`)

**Secondary:**
- Shell (bash) — training orchestration scripts (`scripts/run_training.sh`, `scripts/vast_train.sh`, `scripts/setup_gpu.sh`)

## Runtime

**Environment:**
- Python 3.10+ (local dev), Python 3.11 (Modal cloud containers, Dockerfile)
- Node.js (bundled with Max 8 / Max for Live) — runs `m4l/code/apollo_bridge.js`

**Package Manager:**
- pip with `venv` at `venv/`
- Lockfiles: `requirements.txt` (dev), `requirements-gpu.txt` (pinned GPU training)

## Frameworks

**Core ML:**
- PyTorch 2.3.1 (CUDA 12.1 wheel on GPU, MPS on Apple Silicon)
  - `torch.nn.Module` subclasses for all model components
  - `torch.utils.data.Dataset` / `DataLoader` for training
  - `torch.nn.parallel.DistributedDataParallel` for multi-GPU
  - `torch.cuda.amp.GradScaler` + `torch.autocast` for mixed precision
  - `torch.compile` (optional, Triton backend, ~15-30% speedup)

**Cloud GPU Training:**
- Modal SDK — provisions A100 containers, persistent volumes, remote function execution
  - Entry point: `modal_train.py`
  - Volumes: `apollo-data` (preprocessed .npy), `apollo-checkpoints`

**Audio / MIDI Processing:**
- librosa 0.10.2 — FFT analysis, mel spectrogram extraction, spectral features
- pretty_midi 0.2.10 — MIDI parsing and synthesis
- mido 1.3.2 — MIDI I/O
- soundfile — WAV read/write for synthesis pipeline

**Real-time Bridge:**
- python-osc (`pythonosc`) — OSC server/client for Max for Live communication

**Synthesis Backends (ordered by quality):**
1. FluidSynth CLI + soundfont (external binary, `brew install fluidsynth`)
2. EnCodec neural codec (optional, `pip install encodec`)
3. Pure-Python additive synthesis (built-in fallback, no external deps)

**Testing:**
- pytest — test runner, config in `pytest.ini`

**Build/Dev:**
- ruff — linting (`ruff.toml`: line-length=100, minimal rules F + E9)
- Docker — CUDA training image (`Dockerfile`: `pytorch/pytorch:2.3.0-cuda12.1-cudnn8-runtime`)
- Make — workflow entrypoints (`Makefile`: smoke, preprocess, train, modal-*, install-m4l)
- pre-commit — hooks (`.pre-commit-config.yaml`)

## Key Dependencies

**Critical:**
- `torch==2.3.1` — model, training, and inference; pinned for CUDA ABI compatibility
- `pretty_midi==0.2.10` — MIDI parsing in all data pipelines
- `librosa==0.10.2` — spectral analysis and mel spectrogram extraction
- `python-osc` — OSC bridge between Max for Live and inference server
- `modal` — cloud GPU provisioning for A100 training runs

**Infrastructure:**
- `numpy==1.26.4` — memory-mapped .npy arrays for training data (`mmap_mode='r'`)
- `pandas==2.2.2` — MAESTRO CSV metadata parsing during preprocessing
- `tqdm==4.66.4` — preprocessing progress bars
- `PyYAML==6.0.1` — config loading for all training and inference configs
- `wandb==0.17.0` — optional training metrics (disabled by default, `use_wandb: false`)
- `soundfile` — WAV I/O in synthesis pipeline
- `encodec` — optional neural audio codec polish (`scripts/synthesize.py` backend 2)

## Configuration

**Environment:**
- No `.env` file required for training or inference
- Device auto-detection: MPS (Apple Silicon) → CUDA → CPU in `inference_server.py`
- Modal authentication: `modal setup` (browser OAuth, stored by Modal CLI)

**Build:**
- `configs/base.yaml` — production training (6L/384d, 14.8M params, 50K steps)
- `configs/large.yaml` — large model (8L/512d, ~50M params, 100K steps)
- `configs/v3_mel.yaml` — mel spectrogram conditioning variant
- `configs/v4_streaming.yaml` — streaming note-on/off vocab (259 tokens, 80K steps)
- `configs/smoke.yaml` — local correctness check (2L/128d, 200 steps, ~60s on MPS)
- `configs/inference.yaml` — runtime inference server settings (OSC ports, device, checkpoint path)

## Platform Requirements

**Development:**
- Python 3.10+, pip, venv
- Apple Silicon MPS available for <10ms local inference and smoke tests
- FluidSynth (optional, `brew install fluidsynth`) for audio synthesis
- `modal` CLI (`pip install modal && modal setup`) for cloud GPU access

**Production (Training):**
- Docker image: `pytorch/pytorch:2.3.0-cuda12.1-cudnn8-runtime`
- A100 GPU via Modal; ~$5–15 per base training run (~6 hours)
- MAESTRO v3 dataset: ~56MB MIDI-only, ~101GB with audio

**Production (Inference / M4L):**
- Python 3.10+ with venv at project root (`venv/bin/python3`)
- Ableton Live Suite (or Live + Max for Live add-on) for M4L device
- Inference server runs locally; M4L bridge spawns it as a subprocess

---

*Stack analysis: 2026-05-13*

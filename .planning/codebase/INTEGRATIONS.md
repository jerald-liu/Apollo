# External Integrations

**Analysis Date:** 2026-05-13

## APIs & External Services

**Cloud GPU Compute:**
- Modal (modal.com) — provisions A100 containers, persistent volumes, and runs remote training/preprocessing functions
  - SDK/Client: `modal` Python package
  - Auth: `modal setup` (browser OAuth, stored by Modal CLI)
  - Entry point: `modal_train.py`
  - Volumes: `apollo-data` (preprocessed MAESTRO .npy arrays), `apollo-checkpoints` (model checkpoints)
  - GPU: A100 40GB, CUDA 12.1, ~$5–15 per training run

**ML Experiment Tracking (optional):**
- Weights & Biases (wandb) — training metrics logging
  - SDK/Client: `wandb==0.17.0`
  - Auth: `WANDB_API_KEY` env var or `wandb login`
  - Disabled by default (`use_wandb: false` in all configs); enable per run

## Data Storage

**Datasets:**
- MAESTRO v3.0.0 (local + Modal volume)
  - MIDI: `data/raw/maestro-v3.0.0/` — 1,276 files, 198.7 hours, organized by year (2004–2018)
  - Audio: same directory, ~101GB (not committed to repo, downloaded on demand)
  - Metadata: `data/raw/maestro-v3.0.0/maestro-v3.0.0.csv` — parsed by `scripts/preprocess.py`

**Preprocessed Training Arrays:**
- `data/processed/` — MIDI-only preprocessed (compound token format, vocab=380)
  - `train_tokens.npy` — 35,886 × 513 int32, memory-mapped
  - `validation_tokens.npy` — 4,902 × 513 int32
  - `test_tokens.npy` — 6,351 × 513 int32
  - `train_continuous.npy` — float32 spectral features (present only with `--spectral`)
  - `meta.json` — window count, seq_len, vocab_size, split sizes
- `data/processed_streaming/` — streaming note-on/off format (vocab=259, v4 config)
- `data/processed/generated/` — generated MIDI and WAV samples from evaluation runs

**Model Checkpoints:**
- `models/` — local checkpoint storage (not committed, pulled from Modal volume)
  - `models/checkpoint_a100_best.pt` — active best checkpoint (step 6,999, val loss 2.2683)
  - `models/checkpoint_latest.pt` — latest step checkpoint
  - Checkpoint format: `{'step', 'model_state_dict', 'optimizer_state_dict', 'config', 'best_val_loss', 'train_losses', 'val_losses'}`

**File Storage:**
- Local filesystem for development
- Modal persistent volumes (`apollo-data`, `apollo-checkpoints`) for cloud training

**Caching:**
- NumPy memory-mapped arrays (`mmap_mode='r'`) — OS-level page cache for training data
- Soundfont cache: `~/.apollo/GeneralUser_GS.sf2` — downloaded once by `scripts/synthesize.py`

## Audio Synthesis Pipeline

**FluidSynth (primary backend):**
- External CLI binary: `fluidsynth` (macOS: `brew install fluidsynth`)
- Soundfont: `~/.apollo/GeneralUser_GS.sf2` (auto-downloaded ~30MB) or bundled brew SF2
- Called via `subprocess.run()` in `scripts/synthesize.py`

**EnCodec Neural Codec (optional polish backend):**
- EnCodec 24kHz / 6kbps model (Meta Research)
  - SDK/Client: `encodec` package (`pip install encodec`)
  - Used in `scripts/synthesize.py` as optional neural audio quality pass
  - Also referenced as a planned training head in `src/model.py` (`CodecHead`, Phase 4)
  - No auth required; model weights download on first use via HuggingFace

## Authentication & Identity

**Auth Provider:** None (no user accounts in current implementation)
- Phase 3 plans per-user style embeddings via `user_embed_dim` parameter in `ApolloModel`, but not implemented

## Monitoring & Observability

**Error Tracking:**
- None (no Sentry or similar)
- Errors surfaced via OSC message `/apollo/error` to Max for Live UI

**Logs:**
- `print()` statements throughout (prefixed with `[Apollo]`)
- Max for Live: `Max.post()` in `m4l/code/apollo_bridge.js` → Max console
- Modal: stdout/stderr captured by Modal runner and shown in terminal
- Training: step/loss logged to stdout every `log_interval` steps (default: 50)

## CI/CD & Deployment

**CI Pipeline:**
- GitHub Actions (`.github/workflows/ci.yml`) — runs on push/PR

**Hosting:**
- Training: Modal cloud (A100, ephemeral containers)
- Inference: Local (user's machine), spawned as subprocess by M4L bridge

**Container:**
- `Dockerfile` — `pytorch/pytorch:2.3.0-cuda12.1-cudnn8-runtime` base, mounts `src/`, `scripts/`, `configs/`
- Modal image: `modal.Image.debian_slim(python_version="3.11")` with pip layers for torch and ML deps

**M4L Device Deployment:**
- `make install-m4l` copies `m4l/patchers/` and `m4l/code/` to Ableton User Library
- Default target: `~/Music/Ableton/User Library/Presets/MIDI Effects/Max MIDI Effect/Apollo/`

## OSC Protocol (Max for Live ↔ Inference Server)

**Incoming to inference server (port 7401):**
- `/apollo/note [pitch, velocity, deltaTime, duration, pedal]` — legacy full event
- `/apollo/note_on [pitch, velocity]` — streaming: immediate on keypress
- `/apollo/note_off [pitch]` — streaming: on key release
- `/apollo/pedal [value]` — sustain pedal state
- `/apollo/config [temperature, topK, density, timbreInfluence]` — generation params
- `/apollo/transport [playing, tempo, timeSigNum, timeSigDen]` — Ableton transport state
- `/apollo/model/load [name]` — hot-swap model config
- `/apollo/timbre/offset [brightness, attack, richness]` — timbral descriptor offsets
- `/apollo/bypass [0|1]` — bypass toggle
- `/apollo/cc_map [brightness_cc, attack_cc, richness_cc]` — MIDI CC assignments
- `/apollo/velocity_scale [scale]` — velocity multiplier
- `/apollo/ping` — heartbeat check

**Outgoing from inference server (port 7400):**
- `/apollo/gen/note [pitch, velocity, deltaTimeMs, durationMs, pedal]` — generated note
- `/apollo/gen/cc [ccNumber, ccValue]` — timbral MIDI CC (brightness→74, attack→73, richness→71)
- `/apollo/gen/timbre [brightness, attack, richness, warmth, flux]` — raw timbral descriptors
- `/apollo/status [state, latencyMs]` — time-to-first-event metric
- `/apollo/pong` — heartbeat response
- `/apollo/error [message]` — error report

## Webhooks & Callbacks

**Incoming:** None
**Outgoing:** None

---

*Integration audit: 2026-05-13*

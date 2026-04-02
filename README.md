# Apollo

Real-time AI-powered jamming buddy that responds to your playing with expressive, timbral-aware musical accompaniment.

## What Makes Apollo Different

Most AI music systems operate on notes alone. Apollo treats **timbre, velocity, dynamics, and spectral texture** as first-class features — not just pitch and rhythm. It learns from real expressive performances (not quantized MIDI) and generates responses that include timbral descriptors mapped to synth parameters.

- No hardcoded Western harmony — harmonic patterns are learned, not rule-based
- Per-user style embeddings — Apollo personalizes to your playing over time
- Real-time inference (<10ms per event on Apple Silicon)
- Standalone app + Max For Live plugin (Ableton integration)

## Architecture

```
MIDI Input → Perception → [Autoregressive Transformer] → MIDI Output + Timbral CCs
                              ↑                    ↓
                     Spectral Context         Token Head → pitch, velocity, timing, duration, pedal
                     (FFT trajectory)         Timbre Head → brightness, attack, richness, warmth, flux
                              ↑                              ↓
                     User Embedding            Mapped to MIDI CC → controls synth parameters
```

**Model**: Decoder-only Transformer with dual output heads (token logits + continuous timbral descriptors). Spectral features from paired audio are injected as a continuous side-channel alongside discrete tokens.

**Representation**: 380-token vocabulary encoding musical events as compound tokens (time_shift, pitch, velocity, duration, pedal), with a 21-dimensional continuous spectral feature vector per event (5 note-level descriptors + 16-dim phrase trajectory embedding).

## Project Structure

```
apollo/
├── configs/           # Training configs (base, large)
├── data/
│   ├── raw/           # MAESTRO dataset
│   └── processed/     # Preprocessed token arrays (.npy)
├── models/            # Trained checkpoints
├── notebooks/         # Phase 0 exploration (audit, benchmarks, PoC)
├── scripts/
│   ├── preprocess.py  # MIDI + audio → training data
│   ├── train.py       # GPU training (DDP, AMP, wandb)
│   ├── setup_gpu.sh   # Cloud GPU instance setup
│   └── run_training.sh # One-command training pipeline
├── src/
│   ├── model.py       # ApolloModel (Transformer + spectral encoder + timbre predictor)
│   ├── representation.py  # Event tokenization + continuous features
│   └── spectral.py    # FFT analysis (centroid, flux, rolloff, flatness, trajectory)
└── docs/
    ├── STATUS.md      # Current development status
    └── representation.md  # Detailed representation design doc
```

## Quick Start

### Prerequisites
- Python 3.10+
- PyTorch 2.0+

### Setup
```bash
git clone https://github.com/jerald-liu/Apollo.git
cd Apollo
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### Preprocess MAESTRO
```bash
# Download happens automatically, or place MAESTRO in data/raw/
python scripts/preprocess.py --midi-dir data/raw/maestro-v3.0.0
```

### Train
```bash
# Local (MPS/CPU):
python scripts/train.py --config configs/base.yaml

# Cloud GPU (single A100):
python scripts/train.py --config configs/base.yaml

# Multi-GPU:
torchrun --nproc_per_node=4 scripts/train.py --config configs/base.yaml
```

### Train with Spectral Features
Requires full MAESTRO dataset with audio (~101GB):
```bash
python scripts/preprocess.py \
    --midi-dir data/raw/maestro-v3.0.0 \
    --audio-dir data/raw/maestro-v3.0.0 \
    --spectral

python scripts/train.py --config configs/base.yaml --spectral true
```

## Current Status

**Phase 0 (PoC)**: Complete. Dataset audit, latency benchmarks, trained PoC model, spectral pipeline working.

**Phase 1 (Scale Up)**: In progress. Full MAESTRO preprocessed, GPU training infrastructure ready.

**Phase 2 (Real-time Engine)**: Not started. C++/Rust inference core with MIDI I/O.

**Phase 3 (Personalization)**: Not started. Per-user style embeddings.

**Phase 4 (Applications)**: Not started. JUCE standalone app + Max For Live device.

See [docs/STATUS.md](docs/STATUS.md) for detailed status.

## Datasets

| Dataset | Files | Use | License |
|---|---|---|---|
| [MAESTRO v3](https://magenta.withgoogle.com/datasets/maestro) | 1,276 | Primary training (piano, hardware-captured velocity + pedal + audio) | CC BY-NC-SA 4.0 |
| [GiantMIDI-Piano](https://github.com/bytedance/GiantMIDI-Piano) | 10,855 | Planned — broader repertoire | CC BY 4.0 |
| [GigaMIDI](https://huggingface.co/datasets/Metacreation/GigaMIDI) | 2.1M | Planned — multi-instrument, expressiveness labels | CC BY-NC 4.0 |

## Inspired By

- [SongDriver](https://arxiv.org/abs/2209.06054) — two-phase real-time accompaniment (Transformer + CRF). Apollo borrows the latency-elimination strategy but replaces rule-based harmony with learned representations and adds timbral awareness.

## License

GPL-3.0 (due to JUCE dependency for future standalone/plugin builds). Core ML code is MIT-compatible.

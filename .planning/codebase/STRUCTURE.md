# Codebase Structure

**Analysis Date:** 2026-05-13

## Directory Layout

```
apollo/                        # Project root
├── src/                       # Core Python source — model, inference, representations
│   ├── model.py               # ApolloModel + all nn.Module subclasses
│   ├── representation.py      # Compound token vocab (380), ApolloEvent, encode/decode
│   ├── streaming_representation.py  # Streaming note-on/off vocab (259)
│   ├── spectral.py            # SpectralAnalyzer, SpectralTrajectory, NoteSpectralProfile
│   └── inference_server.py    # Real-time OSC server for Max for Live
├── scripts/                   # Entry-point scripts (not imported as modules)
│   ├── train.py               # GPU training (DDP, AMP, cosine LR, checkpointing)
│   ├── preprocess.py          # MAESTRO MIDI + audio → windowed .npy arrays
│   ├── generate.py            # Post-training generation and evaluation
│   ├── synthesize.py          # MIDI → WAV (FluidSynth / EnCodec / additive)
│   ├── spectral_analysis.py   # Standalone spectral feature inspection
│   ├── check_spec_coverage.py # Verify spectral feature coverage in dataset
│   ├── train_poc.py           # Phase 0 PoC training (legacy)
│   ├── train_spectral.py      # Spectral-aware training variant (legacy)
│   ├── run_training.sh        # One-shot local pipeline (legacy)
│   ├── setup_gpu.sh           # Cloud GPU instance setup
│   └── vast_train.sh          # Vast.ai training variant
├── configs/                   # YAML training and inference configs
│   ├── base.yaml              # Production: 6L/384d, 14.8M params, 50K steps
│   ├── large.yaml             # Large: 8L/512d, ~50M params, 100K steps
│   ├── v2.yaml                # v2 compound token config
│   ├── v3_mel.yaml            # v3 mel spectrogram conditioning
│   ├── v4_streaming.yaml      # v4 streaming note-on/off vocab (259 tokens)
│   ├── smoke.yaml             # Local correctness check: 2L/128d, 200 steps
│   └── inference.yaml         # Runtime inference server settings
├── m4l/                       # Max for Live device
│   ├── patchers/
│   │   └── apollo_engine.maxpat  # Main Max patcher (UI + MIDI routing)
│   ├── code/
│   │   ├── apollo_bridge.js      # Node for Max: OSC relay + Python subprocess mgmt
│   │   ├── apollo_activity.js    # Activity meter JS
│   │   ├── apollo_status.js      # Status display JS
│   │   └── apollo_timbre_meters.js  # Timbral descriptor visualizer JS
│   └── media/                    # Images, icons for device UI
├── data/
│   ├── raw/
│   │   └── maestro-v3.0.0/    # Raw MAESTRO MIDI (+ audio if downloaded), by year
│   ├── processed/             # MIDI-only preprocessed training arrays (.npy)
│   │   ├── train_tokens.npy   # 35,886 × 513 int32 (mmap)
│   │   ├── validation_tokens.npy
│   │   ├── test_tokens.npy
│   │   ├── meta.json          # Window counts, seq_len, vocab_size, split sizes
│   │   └── generated/         # Evaluation MIDI + WAV outputs
│   └── processed_streaming/   # Streaming vocab preprocessed arrays (v4)
├── models/                    # Checkpoints (not committed — pull via make pull-checkpoints)
│   └── checkpoint_a100_best.pt  # Best A100 checkpoint (step 6,999, val loss 2.2683)
├── tests/
│   ├── unit/
│   │   ├── test_model.py
│   │   ├── test_representation.py
│   │   └── test_spectral.py
│   └── integration/
│       ├── test_interfaces.py
│       └── test_preprocess.py
├── notebooks/                 # Phase 0 Jupyter exploration (audit, benchmarks, PoC)
├── specs/                     # Design specifications (interfaces.md, model.md, etc.)
├── docs/                      # Project documentation and artifacts
│   ├── STATUS.md              # Phase completion and next-steps tracker
│   ├── representation.md      # Representation design rationale
│   ├── architecture.html      # System diagrams
│   ├── latency_benchmark.json # Phase 0 latency benchmarks
│   └── maestro_audit.json     # MAESTRO dataset audit results
├── .planning/
│   └── codebase/              # GSD codebase maps (this directory)
├── modal_train.py             # Modal IaC: persistent volumes, preprocess + train fns
├── Dockerfile                 # CUDA 12.1 + PyTorch 2.3 training image
├── Makefile                   # Developer workflow entrypoints
├── requirements.txt           # Dev dependencies (unpinned)
├── requirements-gpu.txt       # Pinned GPU training deps (used by Dockerfile + Modal)
├── requirements-dev.txt       # Dev tooling (pytest, ruff, etc.)
├── ruff.toml                  # Linter config (line-length=100, minimal rules)
├── pytest.ini                 # Test runner config
├── .pre-commit-config.yaml    # Pre-commit hooks
├── .github/workflows/ci.yml   # GitHub Actions CI
└── .dockerignore / .gitignore
```

## Directory Purposes

**`src/`:**
- Purpose: All importable Python modules; the library that scripts and the inference server depend on
- Contains: Model definition, tokenizers, spectral analysis, real-time server
- Key files:
  - `src/model.py` — `ApolloModel`, `CausalTransformer`, `SpectralEncoder`, `MelEncoder`, `TimbrePredictor`
  - `src/representation.py` — compound token format (vocab=380), `ApolloEvent`, `midi_to_events`, `events_to_tokens`, `tokens_to_events`, `events_to_midi`
  - `src/streaming_representation.py` — streaming format (vocab=259), `StreamNoteOn`, `StreamNoteOff`, `encode_note_on`, `encode_note_off`, `streaming_tokens_to_events`
  - `src/spectral.py` — `SpectralAnalyzer`, `SpectralTrajectory`, `NoteSpectralProfile`
  - `src/inference_server.py` — `ApolloInferenceServer` (OSC handlers, generation, model loading)

**`scripts/`:**
- Purpose: Entry-point executables — run from CLI, not imported
- Contains: Data pipeline, training, generation, synthesis
- Key files:
  - `scripts/train.py` — `TrainConfig`, `PreprocessedDataset`, full training loop
  - `scripts/preprocess.py` — MAESTRO → `.npy` pipeline, mel spectrogram extraction
  - `scripts/generate.py` — checkpoint loading, MIDI generation at multiple temperatures
  - `scripts/synthesize.py` — MIDI → WAV (FluidSynth → EnCodec → additive fallback)

**`configs/`:**
- Purpose: YAML configs defining model architecture and training hyperparameters; loaded by `TrainConfig.from_yaml()` and `inference_server.py`
- Model variant naming: `base` (v2 compound), `v3_mel` (mel conditioning), `v4_streaming` (streaming vocab)

**`m4l/`:**
- Purpose: Max for Live device assets — installed to Ableton User Library via `make install-m4l`
- The Max patcher (`m4l/patchers/apollo_engine.maxpat`) handles all MIDI routing, UI, and transport integration
- JS modules in `m4l/code/` implement the OSC bridge and visualizers; no npm deps, uses built-in Node modules only

**`data/`:**
- Purpose: Raw and preprocessed training data; generated evaluation outputs
- `data/raw/` is populated by `scripts/preprocess.py` download logic or manual MAESTRO placement
- `data/processed/` and `data/processed_streaming/` are outputs of preprocessing runs; the `meta.json` is the authoritative manifest for each split

**`models/`:**
- Purpose: Local checkpoint storage; not committed to git
- Pull with `make pull-checkpoints` from Modal volume
- Checkpoint path referenced in `configs/inference.yaml` as `models/checkpoint_a100_best.pt`

**`tests/`:**
- Purpose: Pytest test suite; `unit/` for isolated module tests, `integration/` for pipeline tests
- Run: `pytest` from project root

## Key File Locations

**Entry Points:**
- `scripts/train.py` — training (`make train` / `make modal-train`)
- `scripts/preprocess.py` — data preprocessing (`make preprocess`)
- `src/inference_server.py` — real-time OSC server (`python src/inference_server.py --config configs/inference.yaml`)
- `scripts/generate.py` — generation and evaluation
- `modal_train.py` — Modal cloud training IaC

**Configuration:**
- `configs/inference.yaml` — OSC ports, device, checkpoint path, generation defaults
- `configs/base.yaml` — primary training config (modify here to change model size/training budget)
- `configs/v4_streaming.yaml` — streaming vocab config (active development target)
- `ruff.toml` — linter settings
- `pytest.ini` — test config

**Core Logic:**
- `src/model.py` — all neural network code
- `src/representation.py` — token vocabulary, quantization bins, encode/decode
- `src/streaming_representation.py` — streaming token vocabulary
- `src/spectral.py` — spectral feature extraction
- `m4l/code/apollo_bridge.js` — Max for Live bridge (OSC protocol, Python subprocess)

**Testing:**
- `tests/unit/test_model.py`, `tests/unit/test_representation.py`, `tests/unit/test_spectral.py`
- `tests/integration/test_interfaces.py`, `tests/integration/test_preprocess.py`

## Naming Conventions

**Files:**
- `snake_case.py` for all Python modules and scripts
- `snake_case.js` for Max for Live JS modules (prefixed `apollo_`)
- `snake_case.yaml` for configs, with `v{N}_` prefix for versioned model variants

**Directories:**
- Lowercase, descriptive: `src/`, `scripts/`, `configs/`, `m4l/`, `data/`, `models/`, `tests/`

**Classes:**
- PascalCase: `ApolloModel`, `SpectralAnalyzer`, `CausalTransformerLayer`, `ApolloInferenceServer`

**Constants:**
- UPPER_SNAKE_CASE: `VOCAB_SIZE`, `TOKEN_OFFSETS`, `TOKENS_PER_EVENT`, `SPECTRAL_DIM`

**Functions:**
- `snake_case`: `midi_to_events()`, `events_to_tokens()`, `encode_note_on()`

## Where to Add New Code

**New model component (new conditioning pathway, new head):**
- Implementation: `src/model.py` as a new `nn.Module` subclass
- Wire into `ApolloModel.__init__()` and `forward()`
- Add corresponding config fields to `TrainConfig` in `scripts/train.py`
- Create or update a config file in `configs/`

**New token representation or vocabulary:**
- Implementation: new file `src/{name}_representation.py` following the pattern of `src/streaming_representation.py`
- New preprocessed data dir: `data/processed_{name}/`
- New config: `configs/v{N}_{name}.yaml` with `data_dir` pointing to new processed dir

**New script (evaluation, analysis, etc.):**
- Location: `scripts/{name}.py`
- Import from `src/` using `sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))`

**New OSC handler in inference server:**
- Add `handle_{name}()` method to `ApolloInferenceServer` in `src/inference_server.py`
- Register with `disp.map("/apollo/{name}", self.handle_{name})` in `start()`
- Add corresponding `Max.addHandler("{name}", ...)` in `m4l/code/apollo_bridge.js`

**New unit test:**
- Location: `tests/unit/test_{module}.py`
- New integration test: `tests/integration/test_{scenario}.py`

**New config variant:**
- Location: `configs/v{N}_{descriptor}.yaml`
- Must specify at minimum: `data_dir`, `vocab_size`, `d_model`, `nhead`, `num_layers`, `max_seq_len`, `batch_size`, `lr`, `max_steps`

## Special Directories

**`data/processed/generated/`:**
- Purpose: MIDI and WAV outputs from `scripts/generate.py` evaluation runs
- Generated: Yes (by `scripts/generate.py`)
- Committed: Sample files committed for reference (`.mid` and `.wav` pairs)

**`models/`:**
- Purpose: Local checkpoint storage
- Generated: Yes (by `scripts/train.py` or `make pull-checkpoints`)
- Committed: No (in `.gitignore`; pulled from Modal volume on demand)

**`venv/`:**
- Purpose: Python virtual environment
- Generated: Yes (`python3 -m venv venv`)
- Committed: No

**`.planning/codebase/`:**
- Purpose: GSD codebase analysis maps (STACK.md, INTEGRATIONS.md, ARCHITECTURE.md, STRUCTURE.md)
- Generated: Yes (by GSD map-codebase)
- Committed: Yes

---

*Structure analysis: 2026-05-13*

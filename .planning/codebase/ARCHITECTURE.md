# Architecture

**Analysis Date:** 2026-05-13

## Pattern Overview

**Overall:** Autoregressive decoder-only Transformer with multi-modal conditioning and a real-time OSC inference bridge.

**Key Characteristics:**
- Decoder-only Transformer generates musical events one token at a time, conditioned on prior context
- Dual output heads: discrete token logits (next-event prediction) + continuous timbral descriptors (brightness, attack, richness, warmth, flux)
- Continuous spectral features injected as a learned side-channel alongside token embeddings — timbre treated as a first-class signal, not post-processing
- KV-cache enables O(1) per-step cost after prefill, critical for <10ms real-time inference
- OSC bridge decouples the Python inference server from Max for Live; M4L device spawns the Python subprocess

## Layers

**Token Representation Layer:**
- Purpose: Encodes MIDI events as integer token sequences; defines the vocabulary and quantization bins
- Location: `src/representation.py` (compound, vocab=380), `src/streaming_representation.py` (streaming note-on/off, vocab=259)
- Contains: Quantization bin tables, token offset maps, `ApolloEvent` dataclass, encode/decode functions
- Depends on: `numpy`, `pretty_midi`
- Used by: `scripts/preprocess.py`, `src/inference_server.py`, `scripts/train.py`, `scripts/generate.py`

**Spectral Analysis Layer:**
- Purpose: Extracts per-note and phrase-level timbral features from paired audio, aligned to MIDI events
- Location: `src/spectral.py`
- Contains: `SpectralAnalyzer` (frame-level FFT features), `NoteSpectralProfile`, `SpectralTrajectory` (2s smoothed phrase arcs), normalization helpers
- Depends on: `librosa`
- Used by: `scripts/preprocess.py` (offline), `src/representation.py` (via `midi_to_events`)

**Model Layer:**
- Purpose: The generative Transformer — forward pass, training, and autoregressive generation
- Location: `src/model.py`
- Contains:
  - `ApolloModel` — top-level module wiring all components
  - `CausalTransformer` / `CausalTransformerLayer` / `CausalMHA` — pre-norm causal self-attention stack with KV-cache
  - `SpectralEncoder` — 2-layer MLP projecting 21-dim spectral scalars into token embedding space
  - `MelEncoder` — 2-layer Conv2D encoding log-mel patches into a broadcast context vector (v3 config)
  - `TimbrePredictor` — 2-layer MLP output head predicting 5 continuous timbral descriptors in [0,1]
  - `CodecHead` — 4-codebook EnCodec RVQ prediction head (stub, Phase 4)
- Depends on: `torch`
- Used by: `scripts/train.py`, `src/inference_server.py`, `scripts/generate.py`

**Preprocessing Pipeline:**
- Purpose: Converts raw MAESTRO MIDI (+ optional audio) into memory-mapped .npy training arrays
- Location: `scripts/preprocess.py`
- Contains: `process_file()` (multiprocessing worker), `create_training_windows()` (fixed-length windowing with stride), mel spectrogram extraction
- Depends on: `src/representation.py`, `src/spectral.py`, `pretty_midi`, `librosa`, `pandas`
- Used by: `Makefile` targets `preprocess` and `modal-preprocess`, `modal_train.py`

**Training Layer:**
- Purpose: GPU training with DDP, mixed precision, cosine LR schedule, and checkpointing
- Location: `scripts/train.py`
- Contains: `TrainConfig` dataclass, `PreprocessedDataset` (mmap numpy loader), `augment_tokens()` (pitch/velocity shift), training loop
- Depends on: `src/model.py`, `src/representation.py`, `torch.distributed`, `wandb` (optional)
- Used by: `Makefile`, `modal_train.py`

**Inference Server:**
- Purpose: Real-time OSC server wrapping ApolloModel — receives MIDI events from M4L, generates responses, sends back generated notes and timbral CCs
- Location: `src/inference_server.py`
- Contains: `ApolloInferenceServer` class, OSC handler methods, streaming vs legacy generation paths, KV-cache incremental decode loop
- Depends on: `src/model.py`, `src/representation.py`, `src/streaming_representation.py`, `pythonosc`
- Used by: `m4l/code/apollo_bridge.js` (spawns as subprocess)

**Max for Live Device:**
- Purpose: Ableton Live integration — UI, MIDI capture, Python subprocess lifecycle, OSC relay
- Location: `m4l/patchers/apollo_engine.maxpat`, `m4l/code/apollo_bridge.js`
- Contains: Max patcher (UI + MIDI routing), Node for Max bridge script (OSC encoding, subprocess management, heartbeat)
- Depends on: Node.js `dgram` (UDP), `child_process` (Python subprocess), `max-api`
- Used by: Ableton Live (loaded as MIDI effect device)

## Data Flow

**Training Pipeline:**

1. Raw MAESTRO MIDI files at `data/raw/maestro-v3.0.0/`
2. `scripts/preprocess.py` → `midi_to_events()` extracts `ApolloEvent` list per file (optionally with spectral features via `SpectralAnalyzer`)
3. `events_to_tokens()` → integer token sequence (380 or 259 vocab); `events_to_continuous()` → float32 spectral array
4. `create_training_windows()` → overlapping 512-token windows saved as `data/processed/train_tokens.npy` (+ `train_continuous.npy`, `train_mel.npy`)
5. `scripts/train.py` → `PreprocessedDataset` memory-maps arrays; `DataLoader` batches them
6. `ApolloModel.forward()` computes token logits + optional timbre predictions
7. Cross-entropy loss on next-token prediction + MSE timbre loss → AdamW update
8. Checkpoint saved to `models/` every `save_interval` steps

**Real-time Inference (Streaming Mode):**

1. Performer plays a note in Ableton Live
2. M4L patcher captures MIDI note-on → `Max.outlet("note_on", pitch, velocity)` → `apollo_bridge.js`
3. Bridge encodes `/apollo/note_on [pitch, velocity]` as OSC UDP packet → port 7401
4. `ApolloInferenceServer.handle_note_on()` encodes `StreamNoteOn` → 3 tokens appended to `token_buffer`
5. Spawns generation thread: `_generate_response_streaming()`
6. **Prefill**: full `token_buffer` passed through `ApolloModel.forward()` → builds KV-cache
7. **Decode loop**: single-token steps using KV-cache → O(1) per token; temperature + top-k sampling
8. First decoded note-on event (≥3 tokens) sent immediately: `/apollo/gen/note` OSC → port 7400
9. Bridge receives → `Max.outlet("gen_note", ...)` → M4L patcher plays note via MIDI output
10. Timbral CCs sent as `/apollo/gen/cc [cc_num, cc_val]` → mapped to synth parameters

**Note-off arrives while generation is running:**
- `handle_note_off()` appends 2-token note_off sequence to `token_buffer` (no generation triggered)

**State Management:**
- `ApolloInferenceServer` holds rolling `deque` buffers: `event_buffer` (legacy, 64 events max) and `token_buffer` (streaming, 320 tokens max)
- KV-cache is rebuilt from scratch each generation call — not persisted across calls
- Generation parameters (temperature, top_k, density, timbre_influence) updated live via `/apollo/config` OSC

## Key Abstractions

**ApolloEvent:**
- Purpose: Unified representation of a single musical event with both discrete (pitch, velocity, duration, pedal) and continuous (brightness, attack, richness, warmth, flux, trajectory) fields
- Examples: `src/representation.py` (`ApolloEvent` dataclass)
- Pattern: Dataclass; quantized to tokens via `events_to_tokens()`, continuous features via `events_to_continuous()`

**Compound Token Vocabulary (v2/base):**
- Purpose: Encodes each musical event as exactly 5 tokens [time_shift, pitch, velocity, duration, pedal]; 380 total vocab with timbral token extensions
- Examples: `src/representation.py` (`TOKEN_OFFSETS`, `VOCAB_SIZE=380`)
- Pattern: Single-vocabulary packing with fixed integer offsets per token type

**Streaming Token Vocabulary (v4):**
- Purpose: Splits note-on (3 tokens) and note-off (2 tokens) events so the model sees a keypress immediately without waiting for key release; 259 total vocab
- Examples: `src/streaming_representation.py` (`OFFSETS`, `VOCAB_SIZE=259`)
- Pattern: Interleaved note-on/note-off events ordered by absolute time; 2.5 avg tokens/note vs 5.0 in compound format

**KV-Cache Inference:**
- Purpose: Reduces decode cost from O(T²) to O(T) per step — required for sub-10ms latency targets
- Examples: `src/model.py` (`CausalMHA.forward()` with `past_kv`, `ApolloModel.generate()` prefill/decode split)
- Pattern: Prefill processes full context once; decode loop feeds single token, appending K/V tensors per layer

**SpectralTrajectory:**
- Purpose: Phrase-level timbral arc — smoothed mean/std/delta of 6 spectral features over 2s windows → 16-dim embedding per note onset
- Examples: `src/spectral.py` (`SpectralTrajectory`, `to_embedding()`)
- Pattern: Pre-computed offline during preprocessing; stored in `train_continuous.npy` alongside token arrays

## Entry Points

**Training (Local):**
- Location: `scripts/train.py` (main via `if __name__ == '__main__'`)
- Triggers: `make train`, `python scripts/train.py --config configs/base.yaml`, `torchrun` for DDP
- Responsibilities: Parse `TrainConfig`, build `PreprocessedDataset`, run training loop with AMP + DDP + checkpointing

**Training (Cloud):**
- Location: `modal_train.py` (`train()` and `preprocess()` Modal functions)
- Triggers: `make modal-train CONFIG=configs/v4_streaming.yaml`
- Responsibilities: Provision A100, mount volumes, run remote `train()` function

**Inference Server:**
- Location: `src/inference_server.py` (`main()`)
- Triggers: Spawned by `m4l/code/apollo_bridge.js` subprocess; `python src/inference_server.py --config configs/inference.yaml`
- Responsibilities: Load checkpoint, warm up model, serve OSC requests indefinitely

**Generation / Evaluation:**
- Location: `scripts/generate.py`
- Triggers: `python scripts/generate.py --checkpoint models/checkpoint_best.pt`
- Responsibilities: Load checkpoint, generate MIDI at multiple temperatures, save `.mid` and evaluate stats

**Preprocessing:**
- Location: `scripts/preprocess.py`
- Triggers: `make preprocess`, `make modal-preprocess`
- Responsibilities: Walk MAESTRO directory, tokenize all MIDI files, save windowed .npy arrays

## Error Handling

**Strategy:** Local exceptions caught per-generation-call; errors surfaced as OSC messages to M4L UI rather than crashing the server.

**Patterns:**
- `_generate_response()` and `_generate_response_streaming()` wrap generation in `try/except Exception as e` → `self.osc_client.send_message("/apollo/error", [str(e)])`
- File-not-found on checkpoint load: logs warning and initializes random weights (allows server to start without a checkpoint)
- Soundfont download failure: falls back to additive synthesis silently
- Note token decoding: range validation guards against out-of-vocabulary tokens; invalid events skipped silently

## Cross-Cutting Concerns

**Logging:** `print()` with `[Apollo]` prefix throughout; no structured logging framework. Modal captures stdout/stderr per run.

**Validation:** Token range checks in `tokens_to_events()` (pitch 0–127, velocity 0–31, duration 0–63, pedal 0–3). No input validation layer for OSC messages beyond arg count checks.

**Authentication:** None at server level — OSC server binds to `0.0.0.0:7401` with no auth. Intended for localhost only.

**Thread Safety:** `threading.Lock` guards `event_buffer`, `token_buffer`, `_pending_note_ons`, and `_stream_prev_time` in `ApolloInferenceServer`. Generation runs in daemon threads to avoid blocking the OSC dispatch loop.

**Device Portability:** `_resolve_device()` auto-selects MPS → CUDA → CPU. All tensors created on `self.device`; model loaded with `map_location=self.device`.

---

*Architecture analysis: 2026-05-13*

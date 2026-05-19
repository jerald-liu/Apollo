# Codebase Concerns

**Analysis Date:** 2026-05-13

---

## Tech Debt

**`augment_tokens` hardcodes base-representation token ranges:**
- Issue: `_PITCH_LO/HI = 100, 227` and `_VEL_LO/HI = 228, 259` are hardcoded base-vocab offsets in `scripts/train.py`. These ranges are wrong for the streaming vocab (pitch tokens are 64–151, velocity 152–167). The v4 config already disables augmentation (`pitch_aug_max: 0`, `velocity_aug_range: 0`) with a comment: `# TODO: re-enable once augment_tokens is streaming-vocab-aware`. Until fixed, all v4 streaming training runs forgo pitch/velocity augmentation, limiting generalization.
- Files: `scripts/train.py` lines 111–129, `configs/v4_streaming.yaml` lines 42–43
- Impact: v4 model trains without data augmentation; potential overfitting to seen pitch ranges.
- Fix approach: Accept a `vocab_type` parameter in `augment_tokens` and look up the correct pitch/velocity ranges from the appropriate representation module constants.

**`scripts/train.py` `--resume` flag is declared but not wired:**
- Issue: `--resume` is registered as a CLI argument and documented in the module docstring, but `args.resume` is never read after argument parsing. `start_step` is always `0` and `load_checkpoint` is defined but never called from `train()`. A user following the documented usage (`--resume models/checkpoint_latest.pt`) will silently start training from scratch.
- Files: `scripts/train.py` lines 326, 514–515, 503–508
- Impact: Long A100 training runs cannot be resumed; interrupted runs lose all progress.
- Fix approach: After `config = TrainConfig.from_yaml(...)`, check `args.resume`; call `load_checkpoint(args.resume, raw_model, optimizer)` and set `start_step` from the returned value.

**`CodecHead.upsampler` is always `None`:**
- Issue: `CodecHead` is instantiated with `self.upsampler = None` and a comment saying it is "initialised in train.py when codec rate is known". `train.py` never initialises it. Calling `forward()` with upsampling would raise `TypeError`. Phase 4 (audio codec output) depends on this head being functional.
- Files: `src/model.py` lines 137–138
- Impact: Phase 4 codec output path is entirely unimplemented; `CodecHead` is dead weight in any checkpoint that includes it.
- Fix approach: Either initialise the upsampler in `CodecHead.__init__` with a `scale_factor` parameter, or remove `CodecHead` from the codebase until Phase 4 training begins.

**`generate.py` hardcodes `VOCAB_SIZE = 380` regardless of checkpoint:**
- Issue: `load_checkpoint` in `scripts/generate.py` passes `vocab_size=VOCAB_SIZE` (the base-representation constant, 380) when constructing the model, ignoring `cfg['vocab_size']` from the checkpoint. A streaming-trained checkpoint (vocab 259) loaded via `generate.py` will silently create a model with the wrong embedding table size and fail at `load_state_dict`.
- Files: `scripts/generate.py` lines 36, 49
- Impact: `generate.py` is unusable with any non-base checkpoint without manual source edits.
- Fix approach: Replace `vocab_size=VOCAB_SIZE` with `vocab_size=cfg.get('vocab_size', VOCAB_SIZE)`.

**`modal_train.py` `preprocess` function exposes no `--streaming` flag:**
- Issue: `scripts/preprocess.py` supports `--streaming` to produce the `data/processed_streaming` directory required by `configs/v4_streaming.yaml`. The `modal_train.py::preprocess` function only accepts `spectral` and `mel` booleans and never passes `--streaming` to the subprocess. Streaming preprocessing must be done manually outside Modal.
- Files: `modal_train.py` lines 90, 119–129, 186–187
- Impact: Cannot run streaming preprocessing on the Modal A100 using the standard entrypoint; blocks remote v4 training.
- Fix approach: Add `streaming: bool = False` to `preprocess()` and pass `--streaming` to the `subprocess.run` args when true.

**`modal_train.py` data path derivation breaks for nested `data_dir` values:**
- Issue: The path splitting logic `data_dir.split("/", 1)[-1]` to derive the Modal volume path works for `"data/processed"` → `"processed"` but silently produces a wrong path for multi-level subdirectories: `"data/subdir/processed"` → `"subdir/processed"`, which may not exist on the volume.
- Files: `modal_train.py` lines 154–157
- Impact: Training jobs silently use the wrong data path if a non-standard `data_dir` config is used.
- Fix approach: Strip only the leading `"data/"` prefix explicitly, or require configs to specify a volume-relative path in a separate key.

---

## Known Bugs

**`create_training_windows` call signature mismatch in all tests:**
- Symptoms: Both integration test files call `create_training_windows` with 4 positional arguments and unpack 2 return values. The actual function signature requires 5 positional arguments `(all_tokens, all_continuous, all_onset_times, seq_len, stride)` and returns a 4-tuple `(token_arr, cont_arr, window_times_arr, file_idx_arr)`. Every test that calls this function will raise `TypeError: create_training_windows() missing 1 required positional argument: 'stride'` and the unpacking `tok_arr, cont_arr = ...` would also fail if execution reached it.
- Files: `tests/integration/test_preprocess.py` lines 83, 90, 96, 101, 109, 115, 122–125, 140; `tests/integration/test_interfaces.py` lines 98, 106
- Trigger: Running `pytest tests/ -m integration`
- Workaround: None — tests fail before any assertion is reached.

**EOS token cross-contamination in `_stream_generate_raw`:**
- Symptoms: The streaming generator checks `tok_id in (STREAM_OFFSETS['eos'], TOKEN_OFFSETS['eos'])` to halt. `TOKEN_OFFSETS['eos'] = 378` and `STREAM_OFFSETS['eos'] = 257`. A streaming-trained model (vocab 259) can legitimately generate token 257 (EOS) but will never generate token 378 (it's outside its vocabulary). However, the token 378 check is harmless dead code. The real risk is the inverse: if a base-vocab checkpoint is loaded in streaming mode, token 257 is a velocity token (not EOS), so generation will halt prematurely on any high-velocity note.
- Files: `src/inference_server.py` line 388
- Trigger: Using the wrong checkpoint type for the active representation mode.

**`_BREW_SF2` module-level glob is unreferenced dead code:**
- Symptoms: `synthesize.py` line 41 creates `_BREW_SF2` as a generator from a `Path.glob()` call at module import time, consuming file I/O on every import. The variable is never referenced again — `ensure_soundfont` redoes the same glob inline at lines 58–64. The module-level glob always runs even when FluidSynth is unavailable.
- Files: `scripts/synthesize.py` lines 41, 58–64
- Trigger: Any `import synthesize` call.
- Workaround: Remove line 41.

**Soundfont filename/format mismatch:**
- Symptoms: `SOUNDFONT_PATH` is `~/.apollo/GeneralUser_GS.sf2` but `_SF2_DOWNLOAD_URL` points to `MuseScore_General.sf3` (an SF3, not SF2). FluidSynth requires SF2 format; passing an `.sf3` file to `fluidsynth -ni -F` will fail or produce silence. Additionally, the saved path has the wrong filename (`GeneralUser_GS.sf2` vs the actual downloaded filename `MuseScore_General.sf3`).
- Files: `scripts/synthesize.py` lines 33, 36–38, 71
- Trigger: First run of `synthesize.py` on a machine without the bundled brew soundfont.
- Workaround: Manually download an SF2 (e.g., GeneralUser GS from SourceForge) and place it at `~/.apollo/GeneralUser_GS.sf2`.

---

## Security Considerations

**`torch.load` called with `weights_only=False` in three locations:**
- Risk: `weights_only=False` allows arbitrary Python object deserialization (pickle) from checkpoint files. A maliciously crafted `.pt` file can execute arbitrary code when loaded. This is relevant if checkpoints are ever downloaded from untrusted sources or shared publicly.
- Files: `src/inference_server.py` line 125, `scripts/generate.py` line 45, `scripts/train.py` line 504
- Current mitigation: Checkpoints are currently only produced internally; no public checkpoint download path exists.
- Recommendations: Use `weights_only=True` and save only tensors (not full Python objects) in checkpoint dicts. The `config` dict saved in checkpoints requires special handling — serialize it as JSON in a separate key or save to a sidecar `.json` file.

**OSC server binds on `0.0.0.0`:**
- Risk: The inference server listens on all interfaces (`0.0.0.0`), not just loopback. On a machine with any network exposure, any host on the LAN can send OSC messages to trigger `/apollo/model/load` (arbitrary config loading) or `/apollo/config` (overwrite runtime parameters).
- Files: `src/inference_server.py` line 520
- Current mitigation: Intended for local M4L use only; no authentication or rate limiting.
- Recommendations: Default bind address to `127.0.0.1`; make it configurable via `configs/inference.yaml`.

---

## Performance Bottlenecks

**Thread-per-note spawning with no generation cancellation:**
- Problem: Every `/apollo/note_on` OSC message spawns a new `threading.Thread` targeting `_generate_response_streaming`. At fast playing tempos (e.g., 8+ notes/second), multiple generation threads run concurrently on the same model with no synchronization beyond the buffer lock. Threads complete out-of-order; earlier responses may arrive after later ones.
- Files: `src/inference_server.py` lines 194–195, 221
- Cause: No generation queue, no cancellation token, no "supersede" logic.
- Improvement path: Use a single-worker `queue.Queue` with a generation worker thread; each new note_on discards any in-progress generation and enqueues the new request.

**Prefill is re-run from scratch on every note_on:**
- Problem: `_generate_response_streaming` builds a fresh KV cache from the entire `token_buffer` on every note_on event. For a buffer of 320 tokens and a 6-layer, 384-d model, this is O(T²) attention on every keypress. At 120 BPM with 4 notes/beat, prefill runs 8 times/second.
- Files: `src/inference_server.py` lines 315–358, 360–390
- Cause: The KV cache is not persisted between note_on events; each call rebuilds from scratch.
- Improvement path: Maintain a persistent KV cache across note events; on each new note_on, append only the new tokens to the existing cache (incremental prefill).

**MelEncoder uses a single coarse mel embedding broadcast over all token positions:**
- Problem: `MelEncoder` reduces the entire ~6-second mel patch to a single `(B, 1, d_model)` vector broadcast across all tokens. This provides no temporal resolution within the window; all tokens see the same audio context.
- Files: `src/model.py` lines 48–82
- Cause: `AdaptiveAvgPool2d((8, 8))` aggressively pools spatial structure. Noted in code as "Phase 3.2 will add multi-scale fine/mid/coarse branches."
- Improvement path: Implement multi-scale CNN branches that preserve frame-level resolution for fine conditioning; align mel frames to token positions.

---

## Fragile Areas

**`_expand_spectral_to_tokens` assumes fixed 5-tokens-per-event alignment:**
- Files: `src/model.py` lines 339–365
- Why fragile: The expansion assumes all events produce exactly `tokens_per_event` tokens. With the streaming vocabulary (note_on = 3 tokens, note_off = 2 tokens), this assumption breaks: a sequence of mixed note_on/note_off events has variable tokens-per-event. Passing a streaming batch through a model configured with `spectral_dim > 0` will produce misaligned spectral embeddings.
- Safe modification: Only call with base-vocabulary batches (spectral features are disabled in all streaming configs); do not enable `spectral_dim > 0` in `configs/v4_streaming.yaml`.
- Test coverage: `TestExpandSpectralToTokens` in `tests/unit/test_model.py` only tests the fixed-stride case.

**`handle_model_load` swaps the live model without locking:**
- Files: `src/inference_server.py` lines 266–283
- Why fragile: `/apollo/model/load` replaces `self.model` on the OSC handler thread while a generation thread may be mid-inference on the old model reference. A race condition can cause inference to read from a partially-loaded model or raise `RuntimeError` on the GPU.
- Safe modification: Serialize model swaps with the existing `self.lock`; complete any in-progress generation before swapping.
- Test coverage: No tests for model hot-swap.

**`streaming_tokens_to_events` decoder is stateful and position-sensitive:**
- Files: `src/streaming_representation.py` lines 186–243
- Why fragile: The decoder accumulates `current_time` from time_shift tokens. If the input token sequence contains malformed patterns (e.g., a note_on pitch token without a following velocity token), `i += 1` fallthrough causes time to be advanced by the pitch token value, producing wildly wrong timing for all subsequent notes. This path is hit during inference when the model generates out-of-grammar token sequences.
- Safe modification: Validate each token's expected successor before advancing time; reset or skip on grammar violations.
- Test coverage: No tests for malformed streaming token sequences.

---

## Scaling Limits

**`max_seq_len` position embedding clamping silently degrades quality:**
- Current capacity: `max_seq_len = 512` (base configs), `1024` (large config)
- Limit: When generation runs longer than `max_seq_len` tokens, `position_offset` exceeds `max_seq_len - 1`. Positions are clamped: `pos.clamp(max=self.max_seq_len - 1)`. All out-of-range positions share the same `pos_embedding` vector, destroying positional information for all tokens beyond the window.
- Files: `src/model.py` line 395
- Scaling path: Implement RoPE (rotary positional embeddings) or ALiBi which generalize beyond training length without clamping.

**Token buffer capped at 320 tokens (64 events × 5):**
- Current capacity: `deque(maxlen=max_buffer_events * 5)` = 320 tokens default
- Limit: For streaming vocab (avg 2.5 tokens/note), 320 tokens ≈ 128 notes ≈ ~16 bars at moderate density. Longer musical phrases lose early context.
- Files: `src/inference_server.py` line 73
- Scaling path: Make buffer size configurable in `configs/inference.yaml`; consider separate `max_buffer_tokens` key to account for the streaming vocab token rate.

---

## Dependencies at Risk

**`pretty_midi` — no version pin in `requirements.txt`:**
- Risk: `pretty_midi` (and `mido`) are unpinned. Breaking API changes in either would silently corrupt preprocessing or MIDI output. `pretty_midi` is also unmaintained (last release 2018).
- Impact: MIDI I/O breaks on any `pip install --upgrade`.
- Files: `requirements.txt`
- Migration plan: Pin to `pretty_midi==0.2.10` (matching Modal image pin); evaluate migrating to `symusic` for better maintained MIDI parsing.

**`encodec` listed in `requirements.txt` but optional at runtime:**
- Risk: `pip install encodec` pulls a specific version of `torchaudio` that may conflict with the main `torch` install. The `requirements.txt` lists `encodec` unconditionally, but synthesis code imports it lazily with try/except.
- Files: `requirements.txt`, `scripts/synthesize.py` lines 170–200
- Migration plan: Move `encodec` to an `extras_require` or separate `requirements-encodec.txt` to prevent unintentional installation.

---

## Missing Critical Features

**No streaming preprocessing via Modal remote:**
- Problem: `modal run modal_train.py --action preprocess` does not expose `--streaming`. Running v4 streaming training remotely requires manually SSH-ing into the Modal container or running preprocessing locally.
- Blocks: Remote v4 training on A100.

**No generation script for streaming-vocab models:**
- Problem: `scripts/generate.py` imports `VOCAB_SIZE` from `representation` (380) and passes it hardcoded to `ApolloModel`. It has no streaming decoding path and cannot load a v4 checkpoint. There is no `scripts/generate_streaming.py` equivalent.
- Blocks: Evaluating or auditioning any streaming-trained checkpoint.

**`handle_transport` is a no-op:**
- Problem: Tempo, time signature, and transport state are received via `/apollo/transport` but discarded. The model cannot currently condition on or synchronize with the host DAW tempo.
- Files: `src/inference_server.py` lines 261–264
- Blocks: Beat-synchronous generation; musical phrasing aligned to bar boundaries.

**User embeddings (Phase 2) not yet implemented:**
- Problem: `user_embed_dim: 0` in all configs. `ApolloModel` supports a `user_proj` pathway but it is never trained. Personalization is a stated project goal but has no data collection or training infrastructure.
- Files: `src/model.py` lines 315–316, `configs/base.yaml` line 13

---

## Test Coverage Gaps

**`create_training_windows` tests are entirely broken (wrong arity + wrong unpack):**
- What's not tested: All 8 direct tests of `create_training_windows` in `tests/integration/test_preprocess.py` and 2 in `tests/integration/test_interfaces.py` will fail with `TypeError` before any assertion. The windowing logic (stride, alignment, continuous feature extraction) has zero passing test coverage.
- Files: `tests/integration/test_preprocess.py` lines 83–140, `tests/integration/test_interfaces.py` lines 98–112
- Risk: Silent regressions in preprocessing window creation go undetected.
- Priority: High

**`src/inference_server.py` has zero test coverage:**
- What's not tested: OSC handler logic, streaming generation pipeline, model hot-swap, warmup, device resolution, KV cache behavior in `_stream_generate_raw`, thread safety of buffer mutations.
- Files: `src/inference_server.py` (554 lines, 0 tests)
- Risk: Any regression in the real-time path is only discovered during live performance.
- Priority: High

**`scripts/synthesize.py` has zero test coverage:**
- What's not tested: `ensure_soundfont`, FluidSynth fallback to additive, EnCodec polish path, file extension handling, sample rate behavior.
- Files: `scripts/synthesize.py` (267 lines, 0 tests)
- Risk: Audio output regressions undetected; soundfont URL or format changes silently break synthesis.
- Priority: Medium

**Streaming representation decoder not tested for malformed input:**
- What's not tested: `streaming_tokens_to_events` with missing velocity token after note_on, orphaned note_offs, interleaved corrupt tokens.
- Files: `src/streaming_representation.py` lines 186–243
- Risk: Model-generated malformed sequences cause incorrect timing in real-time output.
- Priority: Medium

---

*Concerns audit: 2026-05-13*

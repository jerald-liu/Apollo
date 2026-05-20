# Phase 2: Model & Training — Context

**Gathered:** 2026-05-19
**Status:** Ready for planning

<domain>
## Phase Boundary

The model layer. The deliverable is a trainable system that takes the pre-tokenized artifact from Phase 1, packs samples as `[MEL_token, BOS, call_tokens, SEP, response_tokens, EOS]`, trains a decoder-only transformer conditioned on a mel embedding, applies loss only to response tokens, and saves a complete checkpoint.

Phase 2 is smoke-tested on **mock pairs only** — no real Ableton corpus yet. Success = the architecture is wired correctly (>95% token-category accuracy on response side, loss visibly lower on response tokens). Phase 3 will bring the real corpus and inference.

**Out of this phase:** real corpus authoring, inference (`generate.py`), sampling controls, evaluation rubric, pitch-shift augmentation. Those are Phases 3–4.

</domain>

<decisions>
## Implementation Decisions

### Mel encoder architecture
- **D-01:** The mel encoder is a small CNN: `Conv2d(1→32, 3×3) → ReLU → MaxPool(2×2) → Conv2d(32→64, 3×3) → ReLU → MaxPool(2×2) → Conv2d(64→128, 3×3) → ReLU → AdaptiveAvgPool2d(1,1) → Flatten → FC(128 → d_model)`. Input shape: `(B, 1, 96, 128)` (add channel dim). Output: `(B, d_model)`.
- **D-02:** The mel encoder is jointly trained with the transformer (no frozen weights). A single forward pass through the mel encoder produces one conditioning vector per sample.
- **D-03:** COND-02 and COND-03 are both satisfied by D-01 and D-02.

### Mel conditioning injection
- **D-04:** The mel vector is injected as a **prefix token at position 0** — a dedicated `MEL` embedding position before BOS. The transformer sequence seen during training is: `[mel_proj, BOS_emb, t1, p1, v1, d1, ..., SEP_emb, t1', p1', v1', d1', ..., EOS_emb]`. The mel vector is linearly projected to d_model and added to a learned positional embedding at position 0.
- **D-05:** No cross-attention. No broadcast-add to all positions. The prefix token approach lets the transformer attention mechanism explicitly "look at" the mel position, is interpretable, and is clean for Phase 3 inference (encode mel once → inject at pos 0 → sample normally).
- **D-06:** Sequence positions start at 0=MEL, 1=BOS, 2..N+1=call tokens, N+2=SEP, N+3..M+3=response tokens, M+4=EOS. The attention mask covers all positions including the MEL prefix.

### Transformer architecture
- **D-07:** Decoder-only transformer (autoregressive / causal). `d_model=128`, `n_layers=4`, `n_heads=4`, `d_ff=512`. This is ~200k parameters — tiny, but sufficient to confirm wiring on 10 mock pairs.
- **D-08:** `max_seq_len=64` (covers MEL + BOS + 24 call tokens + SEP + 24 response tokens + EOS = ~52 positions; 64 gives slack).
- **D-09:** Causal mask only — no cross-attention, no encoder. The MEL prefix is part of the decoder sequence.
- **D-10:** Positional encoding: learned absolute embeddings (simpler than RoPE for Phase 2 scale; RoPE deferred to when context length grows).

### Training sample packing
- **D-11:** Each sample is one call/response pair packed as `[BOS, call_tokens, SEP, response_tokens, EOS]`, then prepended with the MEL embedding at inference time (the MEL prefix is injected in the model forward pass, not in the tokenized sequence). Training input to the model is the token ID sequence; the mel tensor is passed as a separate argument and projected to position 0 by the model.
- **D-12:** Variable-length sequences are padded to `max_seq_len=64` using `PAD_ID=0` (reusing TIME_OFFSET=0, which is otherwise the "time_shift bin 0" token — planner should decide if a dedicated PAD token is needed or if masking is sufficient). Attention mask is `True` for real tokens, `False` for padding.
- **D-13:** DataLoader uses a custom `collate_fn` to pad sequences and stack mel tensors. `batch_size` for smoke train: 4 (with 10 pairs gives 2–3 batches; small enough to expose any batch-shape bugs).

### Loss masking
- **D-14:** Cross-entropy loss is computed on all positions but **zeroed on non-response positions** before the mean. "Response positions" = tokens from SEP+1 through EOS (inclusive). Call tokens, BOS, and SEP are excluded from the gradient. MEL prefix position is also excluded.
- **D-15:** The loss mask is derived from the token ID sequence, not from a hard-coded position offset, so it is robust to variable call lengths.

### Training loop
- **D-16:** Optimizer: `AdamW`, `lr=1e-3`, no LR schedule for the smoke train. Phase 3 real training will add warmup + cosine decay — the training loop must accept a scheduler argument (defaulting to None) so Phase 3 can plug one in without refactoring.
- **D-17:** Gradient clipping: `max_norm=1.0` (standard for transformers, prevents any early-epoch spikes on mock data).
- **D-18:** No mixed precision. Float32 throughout. MPS float16 support is still maturing; the smoke train is fast enough at float32 with a tiny model.
- **D-19:** Device selection: `torch.device("mps")` if `torch.backends.mps.is_available()`, else `"cpu"`. The code must not hard-code CUDA or fail on CPU.

### Smoke-train accuracy gate (TRAIN-04)
- **D-20:** "Next-token type-accuracy on response side" = percentage of response-position predictions where the predicted token ID falls in the **same category** as the target:
  - `[0..31]` → time_shift
  - `[32..68]` → pitch
  - `[69..84]` → velocity
  - `[85..108]` → duration
  - `[109..111]` → special (BOS/EOS/SEP)
  - `[112..255]` → reserved (should not appear; flag if it does)
- **D-21:** The 4-token-per-note packing means token category at each position is deterministic from `(position mod 4)` relative to the sequence start. A model that has learned the packing pattern will nail this; >95% is the "wiring check" gate.
- **D-22:** Metric is computed over the final epoch on the full training set (not a held-out evaluation — smoke train is overfit-by-design; we're checking wiring, not generalization).

### Checkpoint format (TRAIN-06)
- **D-23:** Checkpoint saved as a single `.pt` dict under `models/smoke-{timestamp}.pt` with keys:
  - `model_state_dict` — transformer + positional embedding + output projection
  - `mel_encoder_state_dict` — CNN + FC
  - `vocab` — Vocab dataclass dict (same format as artifact `vocab` dict from Phase 1)
  - `model_config` — `{d_model, n_layers, n_heads, d_ff, max_seq_len, vocab_size}`
  - `training_meta` — `{n_epochs, n_pairs, final_loss, type_accuracy, timestamp}`
- **D-24:** Checkpoint is loaded with `weights_only=False` (trusted local file — same disposition as Phase 1 artifact; document in module docstring).

### Module layout (Claude's Discretion)
- **D-25:** New modules under `apollo/model/`: `mel_encoder.py` (CNN), `transformer.py` (decoder), `packer.py` (dataset packing + DataLoader), `train.py` (training loop), `metrics.py` (type-accuracy computation). CLI script: `apollo/scripts/train_smoke.py`.
- **D-26:** `apollo/model/__init__.py` re-exports the main classes for downstream use by Phase 3 inference.

### Data augmentation
- **D-27:** No augmentation in Phase 2. The pitch-shift ±5 semitones idea from PROJECT.md is explicitly deferred. Smoke train uses mock pairs verbatim.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 1 outputs (the ingest contract Phase 2 consumes)
- `.planning/phases/01-tokenizer-ingest/01-CONTEXT.md` — Phase 1 design decisions (D-01..D-23), especially D-07..D-14 (vocab/token layout), D-11..D-14 (mel shape and padding)
- `.planning/phases/01-tokenizer-ingest/01-01-SUMMARY.md` — What the Vocab dataclass actually contains (VOCAB_SIZE=256, ACTIVE_VOCAB=112, BOS/EOS/SEP=109/110/111)
- `.planning/phases/01-tokenizer-ingest/01-02-SUMMARY.md` — Tokenizer.encode 4-token-per-note packing, round-trip tolerances
- `.planning/phases/01-tokenizer-ingest/01-03-SUMMARY.md` — MelExtractor shape (96, 128), dtype float32, padding value log(1e-8)
- `.planning/phases/01-tokenizer-ingest/01-04-SUMMARY.md` — Artifact schema (schema_version=1, all keys), CLI exit codes
- `.planning/phases/01-tokenizer-ingest/01-05-SUMMARY.md` — synthesize_pair API, ingest() function signature, end-to-end behavior

### Project requirements
- `.planning/REQUIREMENTS.md` — COND-02, COND-03, TRAIN-01..TRAIN-06 are all Phase 2 requirements. Read carefully before planning.

### Vocab constants (load-bearing for model embedding table)
- `apollo/tokenizer/vocab.py` — The single source of truth for token IDs. The embedding table size is `Vocab.VOCAB_SIZE = 256`. Active vocab is `Vocab.ACTIVE_VOCAB = 112`.

</canonical_refs>

<specifics>
## Specific Ideas

- The 4-token-per-note packing `[time_shift, pitch, velocity, duration]` means the model can learn a strict positional grammar. Type-accuracy should climb fast even on tiny data.
- `synthesize_pair` from Phase 1 (`apollo.ingest.mock`) is the mock data source — the Phase 2 training script should use it (or the ingest CLI output) to generate the 10+ mock pairs for smoke training. Don't hard-code fixtures.
- The MEL token at position 0 means `max_seq_len=64` covers: 1 (MEL) + 1 (BOS) + 24 (call, 6 notes × 4 tokens) + 1 (SEP) + 24 (response) + 1 (EOS) = 52, leaving 12 slack. Good.
- Phase 3 inference path: encode mel → project → position 0, then feed `[BOS]` as first input token and sample autoregressively. The model never sees the response tokens at inference time — just the mel prefix + call + SEP, then generates.
- The `packer.py` module is the boundary between Phase 1's artifact format and Phase 2's training DataLoader. Phase 3 inference bypasses the DataLoader entirely.

</specifics>

<deferred>
## Deferred Ideas

- Pitch-shift ±5 semitones augmentation (PROJECT.md) — deferred to Phase 3 when real corpus exists. Requires re-rendering mel tensors, so it's a Phase 3 corpus-management decision.
- LR schedule (warmup + cosine decay) — deferred to Phase 3 real training. Phase 2 smoke train uses constant lr=1e-3.
- Mixed precision (torch.autocast MPS) — deferred until MPS float16 is more stable.
- Top-k / temperature sampling — Phase 3 (inference).
- Multi-epoch training beyond the smoke gate — Phase 3 (real corpus).
- Gradient checkpointing, compilation (`torch.compile`) — not needed at this scale.

</deferred>

---
*Phase: 02-model-training*
*Context gathered: 2026-05-19 via /gsd-discuss-phase 2*

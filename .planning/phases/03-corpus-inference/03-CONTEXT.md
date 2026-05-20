# Phase 3: Corpus & Inference — Context

**Gathered:** 2026-05-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Two parallel workstreams, both required before Phase 4:

1. **Corpus authoring (human):** Author ≥30 Ableton Operator call/response pairs and commit them to `data/pairs/`. This is rate-limited by Ableton authoring time — no code changes needed.

2. **Inference + real training (code):** Build `apollo/scripts/generate.py` (autoregressive inference CLI) and `apollo/scripts/train.py` (real training script, replacing the smoke-train-only `train_smoke.py`). Both must be working before Phase 4 evaluation can begin.

**Out of scope:** Evaluation rubric, hold-out scoring, iteration tracking, pitch-shift augmentation. Those are Phase 4 / later corpus expansion.

</domain>

<decisions>
## Implementation Decisions

### Corpus authoring conventions

- **D-01:** All v1 pairs authored at **120 BPM**. The code enforces ±2 BPM tolerance in `load_notes` — 120 BPM keeps time-bin quantization consistent and matches the smoke-train fixture.
- **D-02:** **Varied Operator presets** across pairs (bright plucks, soft pads, percussive FM tones, etc.). Forces the model to learn that the right response depends on timbre, not just note pattern — the core purpose of mel conditioning.
- **D-03:** **Free key/scale** per pair — author naturally without a fixed tonal center. The tokenizer uses absolute pitch bins, so key variety is not a structural problem.
- **D-04:** **Target gesture length: 0.5–1.5s, 2–6 notes per side** — matches PROJECT.md "tiny gesture" spec and fits within `max_seq_len=64` (24 call tokens + 24 response tokens max).
- **D-05:** **Varied response relationship types** per pair (echo, contrast, continuation, etc.) — author naturally; "Jerald-shape" is the implicit target, not a labeled relationship category.
- **D-06:** **Same or different Operator preset** on call vs. response is a free choice per pair and a user choice at inference time. The model sees both cases; at inference the user picks the response preset in Ableton. No constraint enforced.
- **D-07:** **Pitch-shift augmentation deferred** (D-27 from Phase 2 carried forward). Requires re-rendering `call.wav` for each pitch-shifted variant — too much manual overhead before the basic loop is proven. Revisit in Phase 5 or v2 corpus expansion.

### Real training script

- **D-08:** New script `apollo/scripts/train.py` (separate from `train_smoke.py`). `train_smoke.py` remains as the CI wiring check; `train.py` is for real corpus runs.
- **D-09:** **LR schedule: linear warmup + cosine decay.** `train_epoch` already accepts `scheduler=None` (D-16, Phase 2) — plug in `torch.optim.lr_scheduler.OneCycleLR` or equivalent. Warmup over first ~5% of total steps, cosine to near-zero by end.
- **D-10:** **Checkpoint naming: `models/run-{iteration:02d}-{timestamp}.pt`** (Claude's discretion). Iteration number tracks which corpus version was used (iteration 1 = first 30 pairs, iteration 2 = after adding more). Makes Phase 4 comparison across iterations natural. Timestamp disambiguates reruns within the same iteration.
- **D-11:** **Default 300 epochs** (configurable via `--epochs` flag). Tiny corpus + tiny model = ~60 steps/epoch; 300 epochs ≈ 18k steps, enough to see meaningful loss descent without overfit-watch.
- **D-12:** **Log held-out loss every N epochs** (configurable, default every 10 epochs). Phase 1 already splits into train/held_out; cheap to track. Log to console and optionally to a per-run CSV under `logs/`. Gives early overfitting signal before Phase 4 listen-test.

### Inference / generate.py

- **D-13:** **BPM from call MIDI file.** `load_notes` already reads the call MIDI's estimated tempo. Pass that BPM to `decode_tokens(ids, vocab, tempo_bpm=call_bpm)` so response timing is consistent with the call. No `--bpm` flag needed for v1 (all pairs are 120 BPM anyway, but reading it from the file is correct by design).
- **D-14:** **Autoregressive sampling: temperature=0.8, top-k=10** as defaults, both overridable via CLI flags. Applied as: scale logits by `1/temperature`, zero all but top-k, softmax, sample.
- **D-15:** **Stop condition: EOS token OR max_tokens** (default `max_tokens=24`, i.e. 6 notes × 4 tokens), whichever comes first. Prevents runaway generation if the model doesn't converge to EOS early in training.
- **D-16:** **Invalid token handling: skip and continue.** If the model emits an out-of-range token ID or a token in the wrong 4-slot position (time/pitch/velocity/duration), skip it silently and keep sampling. Partial output is better than a crash during early iteration. Log a warning count at the end.
- **D-17:** **N-sample output: `response_001.mid`, `response_002.mid`, … written to the same directory as `call.mid`.** Zero-padded for file-manager sorting. Existing `response_NNN.mid` files are not overwritten — generate.py finds the next available index. Default N=1 (single response); `--n` flag for batch.

### Claude's Discretion

- `train.py` CLI flag design (beyond `--epochs`, `--checkpoint`, `--n` for generate.py): Claude picks sensible flag names following argparse conventions.
- Log CSV format for per-run training history.
- Whether `generate.py` emits any human-readable summary alongside the MIDI (e.g. "Generated 4 notes, 0 invalid tokens skipped").

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 1 & 2 contracts (inference consumes both)
- `.planning/phases/01-tokenizer-ingest/01-CONTEXT.md` — D-07..D-14 (vocab/token layout), mel shape/padding
- `.planning/phases/01-tokenizer-ingest/01-02-SUMMARY.md` — Tokenizer.encode 4-token-per-note packing; this is the token stream generate.py must decode
- `.planning/phases/01-tokenizer-ingest/01-03-SUMMARY.md` — MelExtractor shape (96, 128), required for inference mel extraction from call.wav
- `.planning/phases/01-tokenizer-ingest/01-04-SUMMARY.md` — Artifact schema (schema_version=1); inference loads call tokens + mel from the artifact
- `.planning/phases/02-model-training/02-CONTEXT.md` — D-04/D-05 (MEL prefix injection), D-07..D-10 (model shape), D-23/D-24 (checkpoint format)
- `.planning/phases/02-model-training/02-02-SUMMARY.md` — ApolloModel forward signature: `(token_ids, mel_input, key_padding_mask)` → logits
- `.planning/phases/02-model-training/02-05-SUMMARY.md` — Checkpoint 5-key format; load_checkpoint API

### Key source files for inference
- `apollo/tokenizer/decoder.py` — `decode_tokens(ids, vocab, tempo_bpm)` — the token→Note decode path. Strips BOS/SEP/EOS before calling. Silently drops partial trailing groups.
- `apollo/tokenizer/vocab.py` — Token ID layout (BOS=109, EOS=110, SEP=111, active vocab=112)
- `apollo/ingest/midi.py` — `load_notes` — reads call MIDI BPM; use this to get `tempo_bpm` for decode_tokens
- `apollo/ingest/audio.py` — MelExtractor; inference calls this on call.wav to get the conditioning tensor
- `apollo/model/__init__.py` — Re-exports ApolloModel, MelEncoder, load_checkpoint, collate_fn

### Project requirements
- `.planning/REQUIREMENTS.md` — DATA-05, INFER-01..INFER-04 are the Phase 3 requirements

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `apollo/tokenizer/decoder.py:decode_tokens` — Already built. Takes stripped response token list + BPM, returns `Note` objects with absolute seconds timing. Inference wraps this directly.
- `apollo/ingest/audio.py:MelExtractor` — Already built. Produces `(96, 128)` float32 mel from a `.wav` file. Inference calls this on `call.wav`.
- `apollo/ingest/midi.py:load_notes` — Already built. Reads call MIDI, enforces tempo tolerance, returns sorted `Note` list. Also extracts BPM estimate for D-13.
- `apollo/model/train.py:train_epoch` — `scheduler=None` parameter already wired (D-16, Phase 2). `train.py` passes a real scheduler; `train_smoke.py` keeps `None`.
- `apollo/scripts/train_smoke.py` — Reference implementation for `train.py`; copy the CLI structure, upgrade the configurability.

### Established Patterns
- `pretty_midi` for MIDI I/O (Phase 1). `generate.py` writes response MIDI using `pretty_midi.PrettyMIDI` — consistent with existing ingest code.
- `argparse` for CLI scripts (train_smoke.py uses it). `train.py` and `generate.py` follow same pattern.
- `venv/bin/python -m pytest` test runner; new tests go in `tests/`.

### Integration Points
- Inference pipeline: `call.wav` → `MelExtractor` → `(96,128)` mel → `collate_fn` unsqueeze → `(1,1,96,128)` → `ApolloModel.mel_enc` → MEL prefix → autoregressive sample → strip BOS/SEP/EOS → `decode_tokens` → `Note` list → `pretty_midi` → `response_NNN.mid`
- `load_checkpoint` returns `model_config` dict; reconstruct `ApolloModel(**model_config)` then `load_state_dict` as shown in Phase 2 round-trip test.

</code_context>

<specifics>
## Specific Ideas

- Response MIDI files written as `response_001.mid`, `response_002.mid`, … alongside `call.mid` / `call.wav` in the same pair directory. Non-destructive: generate.py finds next available index rather than overwriting.
- Training loss + held-out loss logged to console every 10 epochs and optionally to `logs/run-{iteration}-{timestamp}.csv` for Phase 4 trend analysis.
- `train.py` should print a one-line summary at the end: corpus size, epochs, final train loss, final held-out loss, checkpoint path saved.

</specifics>

<deferred>
## Deferred Ideas

- **Pitch-shift augmentation** (D-27, Phase 2) — Deferred again. Requires re-rendering `call.wav` for each shifted variant. Revisit in v2 or when corpus exceeds 100 pairs and more variety is needed.
- **generate.py CLI design** (area not selected for discussion) — Flag names, progress reporting, and summary output are Claude's discretion per the decisions above.
- **FM patch generation head** — Tracked as SEED-001 and backlog item 999.1. Not Phase 3 scope.

</deferred>

---

*Phase: 03-corpus-inference*
*Context gathered: 2026-05-20*

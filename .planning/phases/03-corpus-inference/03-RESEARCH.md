# Phase 3: Corpus & Inference — Research

**Researched:** 2026-05-19
**Domain:** Autoregressive MIDI generation, training CLI, corpus authoring conventions
**Confidence:** HIGH (all findings verified against live source code and planning artifacts)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** All v1 pairs authored at 120 BPM. load_notes enforces ±2 BPM tolerance. 120 BPM keeps time-bin quantization consistent.
- **D-02:** Varied Operator presets across pairs. Forces model to learn timbre-dependent responses.
- **D-03:** Free key/scale per pair. Tokenizer uses absolute pitch bins.
- **D-04:** Target gesture length: 0.5–1.5s, 2–6 notes per side. Fits within max_seq_len=64.
- **D-05:** Varied response relationship types per pair (echo, contrast, continuation, etc.).
- **D-06:** Same or different Operator preset on call vs. response is a free choice per pair.
- **D-07:** Pitch-shift augmentation deferred.
- **D-08:** New script `apollo/scripts/train.py` (separate from `train_smoke.py`). `train_smoke.py` remains for CI.
- **D-09:** LR schedule: linear warmup + cosine decay. Use `torch.optim.lr_scheduler.OneCycleLR` or equivalent. Warmup over first ~5% of total steps, cosine to near-zero by end. Plugs into `train_epoch(scheduler=...)` parameter.
- **D-10:** Checkpoint naming: `models/run-{iteration:02d}-{timestamp}.pt`.
- **D-11:** Default 300 epochs (configurable via `--epochs` flag).
- **D-12:** Log held-out loss every N epochs (configurable, default every 10 epochs). Log to console and optionally to `logs/run-{iteration}-{timestamp}.csv`.
- **D-13:** BPM from call MIDI file. Pass to `decode_tokens(ids, vocab, tempo_bpm=call_bpm)`.
- **D-14:** Autoregressive sampling: temperature=0.8, top-k=10 as defaults, overridable via CLI flags.
- **D-15:** Stop condition: EOS token OR max_tokens (default max_tokens=24, i.e. 6 notes × 4 tokens).
- **D-16:** Invalid token handling: skip and continue. Log a warning count at the end.
- **D-17:** N-sample output: `response_001.mid`, `response_002.mid`, … written to the same directory as `call.mid`. Non-destructive (find next available index). Default N=1; `--n` flag for batch.

### Claude's Discretion

- `train.py` CLI flag design (beyond `--epochs`, `--checkpoint`, `--n` for generate.py).
- Log CSV format for per-run training history.
- Whether `generate.py` emits a human-readable summary alongside the MIDI.

### Deferred Ideas (OUT OF SCOPE)

- Pitch-shift augmentation (D-07 / D-27 from Phase 2).
- `generate.py` CLI design beyond decisions above.
- FM patch generation head (SEED-001).
- Evaluation rubric, hold-out scoring, iteration tracking (Phase 4).
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DATA-05 | Corpus reaches ≥30 authored pairs before first real training run | Human authoring task; no code changes. data/pairs/ does not yet exist — planner creates it as a directory stub and documents authoring conventions. |
| INFER-01 | `generate.py` accepts a path to `call.mid` + `call.wav` and emits `response.mid` | Full pipeline mapped: MelExtractor → collate_fn manual unsqueeze → ApolloModel.forward → strip BOS/SEP/EOS → decode_tokens → pretty_midi write |
| INFER-02 | Response length is configurable (max events or max seconds budget) | Implemented via `--max-tokens` CLI flag (default 24 = 6 notes × 4 tokens per D-15) |
| INFER-03 | Sampling supports temperature and top-k controls | Implemented via `--temperature` and `--top-k` CLI flags (defaults 0.8 / 10 per D-14) |
| INFER-04 | Optional: sample N responses per call to let the user pick a preferred one | Implemented via `--n` flag per D-17; output files response_001.mid, response_002.mid, … |
</phase_requirements>

---

## Summary

Phase 3 has two parallel workstreams. The **corpus authoring** workstream (DATA-05) is a human task with no code changes — the planner documents conventions and creates the `data/pairs/` directory stub. The **code workstream** delivers two new scripts: `apollo/scripts/generate.py` (autoregressive inference CLI) and `apollo/scripts/train.py` (production training script replacing the smoke-only `train_smoke.py`).

All infrastructure for inference already exists. `decode_tokens`, `MelExtractor`, `load_notes`, `load_checkpoint`, `ApolloModel.forward`, and `collate_fn` are fully implemented and tested. Phase 3 code is primarily **wiring** — assembling these components into CLI scripts with the sampling loop being the only net-new algorithm.

The autoregressive loop is a standard token-by-token greedy/sampling approach. The model's `forward` pass is called repeatedly with a growing prefix. There is no KV-cache; the model re-runs the full transformer over the growing sequence on each step. This is acceptable given max_tokens=24 and the tiny model size (~1M params).

**Primary recommendation:** Plan two code tasks (generate.py, train.py) plus one corpus task (directory stub + authoring convention doc). Keep each code task as a single TDD-green unit. Do not split generate.py into sub-tasks — it is ~100 lines of wiring with no architectural uncertainty.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Mel extraction from call.wav | Ingest (MelExtractor) | — | Already built in Phase 1; inference calls it directly |
| Token sequence packing for inference | Inference script (manual) | Packer collate_fn (reference) | collate_fn expects a batch from Dataset; inference manually constructs single-sample tensors |
| Autoregressive sampling loop | Inference script | ApolloModel.forward | Model provides logits; inference script applies temperature/top-k and samples |
| Token → MIDI decode | Tokenizer (decode_tokens) | — | Already built in Phase 1; generates Note list |
| MIDI file write | Inference script (pretty_midi) | — | Same library as ingest; consistent I/O pattern |
| BPM extraction from call MIDI | Ingest (load_notes) | — | Already built; `load_notes` reads estimated tempo |
| LR scheduling | train.py | train_epoch(scheduler=) | Plug point already wired in Phase 2; train.py injects OneCycleLR |
| Held-out loss logging | train.py | ApolloDataset(split="held_out") | Existing split infrastructure; train.py adds a periodic eval pass |
| Checkpoint naming | train.py | save_checkpoint | D-10 naming convention; save_checkpoint already creates parent dirs |
| Corpus directory authoring | Human (Ableton) | data/pairs/ directory stub | No code; planner documents conventions for the human authoring step |

---

## Standard Stack

### Core (all already installed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| torch | 2.x (MPS) | Model forward pass, tensor ops, sampling | Project-wide; MPS confirmed working |
| torchaudio | 2.x | MelExtractor (already used) | Project-wide |
| pretty_midi | 0.2.11 | MIDI read (load_notes) and write (response MIDI) | Already used in Phase 1; consistent I/O |
| argparse | stdlib | CLI flag parsing | Matches train_smoke.py pattern |

[VERIFIED: live source — all imports present in existing scripts]

### No New Dependencies
Phase 3 introduces no new pip packages. All required libraries are already in the project venv.

---

## Architecture Patterns

### Inference Pipeline (End-to-End)

```
call.mid ──► load_notes() ──► call_bpm (float)
                                │
call.wav ──► MelExtractor() ──► mel (96, 128) ──► .unsqueeze(0).unsqueeze(0) ──► (1, 1, 96, 128)
                                                                                      │
                                                                                      ▼
[BOS] ──► grow token prefix ──────────────────────────────────────────► ApolloModel.forward()
                                                                              │
                                                                         logits (1, T, 256)
                                                                              │
                                                              temperature scale + top-k zero + softmax
                                                                              │
                                                                        torch.multinomial
                                                                              │
                                                                       next_token_id
                                                                              │
                                              ┌───── EOS or len >= max_tokens ─────┐
                                              │                                     │
                                           STOP                             append to prefix
                                              │
                                       response_ids (after stripping SEP, EOS, BOS)
                                              │
                                       decode_tokens(ids, vocab, tempo_bpm=call_bpm)
                                              │
                                         List[Note]
                                              │
                                      pretty_midi.PrettyMIDI()
                                              │
                                      response_001.mid
```

### Sampling Loop Detail

The loop starts with `prefix = [BOS]` and no SEP — generate.py is producing the response side independently, not feeding the call tokens in. Wait: this needs careful reading of the CONTEXT.

**CONTEXT.md line 98:** "Inference pipeline: `call.wav` → `MelExtractor` → `(96,128)` mel → `collate_fn` unsqueeze → `(1,1,96,128)` → `ApolloModel.mel_enc` → MEL prefix → autoregressive sample → strip BOS/SEP/EOS → `decode_tokens` → `Note` list → `pretty_midi` → `response_NNN.mid`"

The call tokens are conditioned on via the mel spectrogram (which encodes the call's audio timbre). The model then generates a response autoregressively. The prefix at inference time should be `[BOS, call_tokens..., SEP]` to give the model the call context in token form as well. This matches the training layout `[BOS, call_tokens, SEP, response_tokens, EOS]`.

[VERIFIED: packer.py — training layout is BOS + call + SEP + response + EOS. Inference must match this prefix to activate the response-generating behavior.]

**Correct inference prefix:** `[BOS, call_token_ids..., SEP]` — then sample response tokens one at a time until EOS or max_tokens.

```python
# Source: packer.py layout + ApolloModel.forward contract
# Build inference prefix: [BOS, call_tokens..., SEP]
prefix = [BOS] + list(call_token_ids) + [SEP]
generated = []

for _ in range(max_tokens):
    ids_tensor = torch.tensor([prefix + generated], dtype=torch.long, device=device)
    # mel: (1, 1, 96, 128) — no pad mask needed for single-sample inference
    with torch.no_grad():
        logits = model(ids_tensor, mel, key_padding_mask=None)
    # logits shape: (1, T, 256); next-token logit is at position T-1
    next_logit = logits[0, -1, :]           # (256,)
    # Temperature + top-k
    next_logit = next_logit / temperature
    top_k_vals, top_k_ids = torch.topk(next_logit, k=top_k)
    probs = torch.softmax(top_k_vals, dim=-1)
    chosen_idx = torch.multinomial(probs, num_samples=1)
    next_id = top_k_ids[chosen_idx].item()
    if next_id == EOS:
        break
    generated.append(next_id)

# Strip any stray BOS/SEP/EOS from generated list before decode_tokens
response_ids = [t for t in generated if t not in (BOS, SEP, EOS)]
```

[VERIFIED: ApolloModel.forward returns (B, T, vocab_size). Last position T-1 is the prediction for token T, i.e., the next token after the full prefix.]

### Invalid Token Handling (D-16)

decode_tokens raises `ValueError` on out-of-range token IDs (per-slot validation). The "skip and continue" decision (D-16) is about the sampling loop, not decode_tokens. If the generated list contains tokens in the wrong 4-slot position (e.g., a pitch token where a time-shift token is expected), decode_tokens will raise on the group boundary.

**Implementation approach:** Rather than trying to validate mid-stream in the sampling loop, collect all generated IDs and call decode_tokens in a try/except. If it raises, attempt to decode as many complete valid 4-groups as possible (truncate to `len(response_ids) // 4 * 4` IDs). Log warning count of skipped tokens. This is simpler than slot-position validation in the sampling loop.

[VERIFIED: decoder.py line 42 — `while i + 3 < len(ids)` drops trailing partial groups silently; ValueError raised only on range violations. Wrapping in try/except + truncation satisfies D-16.]

### train.py Structure

`train.py` follows `train_smoke.py` structure but:
1. Loads a real artifact from `data/pairs/` (not synthesized mock pairs)
2. Uses `ApolloDataset(artifact, split="train")` and separately `ApolloDataset(artifact, split="held_out")`  
3. Builds `OneCycleLR` scheduler and passes it to `train_epoch`
4. Logs train + held-out loss every N epochs (D-12)
5. Saves checkpoint with naming convention `models/run-{iteration:02d}-{timestamp}.pt` (D-10)

```python
# Source: train_smoke.py pattern + D-09 scheduler plug point
# OneCycleLR requires total_steps at construction
steps_per_epoch = len(train_loader)
total_steps = n_epochs * steps_per_epoch
scheduler = torch.optim.lr_scheduler.OneCycleLR(
    optimizer,
    max_lr=lr,
    total_steps=total_steps,
    pct_start=0.05,       # 5% warmup
    anneal_strategy="cos",
)
# Pass to train_epoch per D-16 (Phase 2) plug point:
mean_loss = train_epoch(model, train_loader, optimizer, device, scheduler=scheduler)
```

[VERIFIED: train.py line 119 — `if scheduler is not None: scheduler.step()` is called after each batch. OneCycleLR.step() is called per-step, which matches its API correctly.]

### Recommended Project Structure

```
apollo/scripts/
├── train_smoke.py    # existing — CI/smoke only
├── train.py          # NEW — production training CLI
└── generate.py       # NEW — inference CLI

data/
└── pairs/            # NEW directory stub — human authors populate
    ├── 001/
    │   ├── call.mid
    │   ├── call.wav
    │   └── response.mid
    ├── 002/
    ...
    └── 030/          # minimum before first real train run (DATA-05)

logs/                 # NEW — per-run training CSVs
    └── run-01-20260520T120000Z.csv

models/               # existing (gitignored)
    └── run-01-20260520T120000Z.pt
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Warmup + cosine LR schedule | Custom scheduler loop | `torch.optim.lr_scheduler.OneCycleLR` | Handles warmup fraction, cosine annealing, and per-step calls correctly |
| Mel extraction | Custom DSP | `MelExtractor()` (already built) | Full Phase 1 contract: size cap, resample, fixed shape |
| MIDI read for BPM | Manual parse | `load_notes()` (already built) | Enforces tempo tolerance, monophonic guard, returns Note list + estimated BPM |
| MIDI write | Custom byte writer | `pretty_midi.PrettyMIDI()` | Same library used in mock.py; handles tick conversion correctly |
| Token decode | Custom decode loop | `decode_tokens()` (already built) | Per-slot range validation, cursor accumulation, partial-group drop |
| Top-k sampling | Custom sort | `torch.topk()` + `torch.multinomial()` | Numerically correct, differentiable if needed |

**Key insight:** Phase 3 code tasks are wiring, not invention. Every sub-component exists and is tested. The only net-new code is the sampling loop (30-40 lines) and the train.py held-out eval loop.

---

## API Contracts (Verified Against Source)

### decode_tokens

```python
# Source: apollo/tokenizer/decoder.py
def decode_tokens(ids: List[int], vocab: Vocab, tempo_bpm: float = 120.0) -> List[Note]:
```

- **Input:** Flat int list. BOS/SEP/EOS must be stripped BEFORE calling. Partial trailing groups (len not divisible by 4) are dropped silently.
- **Validation:** Raises `ValueError` if any token falls outside its slot's range window.
- **Output:** `List[Note]` with `.pitch`, `.velocity`, `.start` (absolute seconds), `.end` (absolute seconds).

[VERIFIED: decoder.py lines 26–66]

### ApolloModel.forward

```python
# Source: apollo/model/transformer.py
def forward(
    self,
    token_ids: torch.Tensor,                       # (B, T) int64
    mel_input: torch.Tensor,                       # (B, 1, 96, 128) float32
    key_padding_mask: torch.Tensor | None = None,  # (B, T) bool
) -> torch.Tensor:                                 # (B, T, vocab_size)
```

- `key_padding_mask=None` is valid — no padding in single-sample inference.
- Inference call: `model(ids_tensor, mel, key_padding_mask=None)` where `ids_tensor.shape = (1, T)` and `mel.shape = (1, 1, 96, 128)`.
- Output: `(1, T, 256)` — use `logits[0, -1, :]` for next-token logit.

[VERIFIED: transformer.py lines 87–153]

### load_checkpoint / model reconstruction

```python
# Source: apollo/model/train.py
ckpt = load_checkpoint("models/run-01-....pt", map_location="cpu")
# 5 keys: model_state_dict, mel_encoder_state_dict, vocab, model_config, training_meta
model = ApolloModel(**ckpt["model_config"])
model.load_state_dict(ckpt["model_state_dict"])
model.eval()
```

[VERIFIED: train.py lines 183–190; 02-05-SUMMARY.md checkpoint round-trip test]

### MelExtractor call signature

```python
# Source: apollo/ingest/audio.py
mx = MelExtractor()
mel = mx(wav_path: str, pair_path: str)  # returns (96, 128) float32
# For inference, unsqueeze twice:
mel_batch = mel.unsqueeze(0).unsqueeze(0)  # (1, 1, 96, 128)
```

[VERIFIED: audio.py lines 61–102]

### load_notes BPM extraction

```python
# Source: apollo/ingest/midi.py
notes = load_notes(mid_path: str, pair_path: str, tempo_bpm: float = 120.0) -> List[Note]
# BPM is NOT returned by load_notes directly.
# Use pretty_midi.PrettyMIDI(mid_path).estimate_tempo() directly to get call_bpm.
# load_notes uses it for validation; generate.py needs to call estimate_tempo separately.
```

**CRITICAL NOTE:** `load_notes` does NOT return the estimated BPM — it only validates against the configured `tempo_bpm`. To extract the BPM for `decode_tokens`, generate.py must call `pretty_midi.PrettyMIDI(str(call_mid_path)).estimate_tempo()` directly. All pairs are 120 BPM (D-01), so defaulting to 120.0 is safe, but reading from the file is correct by design (D-13).

[VERIFIED: midi.py lines 44–120 — no BPM return value in signature or body]

### collate_fn for inference (manual construction)

`collate_fn` expects a list of `(call_tokens_tensor, response_tokens_tensor, mel_tensor)` tuples and is DataLoader-oriented. For inference, manually construct the prefix tensor:

```python
# Source: packer.py — reverse-engineering the expected layout
from apollo.model import BOS, SEP, EOS
call_ids = torch.tensor(call_token_ids, dtype=torch.long)  # from artifact or freshly encoded
prefix_ids = torch.cat([
    torch.tensor([BOS], dtype=torch.long),
    call_ids,
    torch.tensor([SEP], dtype=torch.long),
])  # shape: (1 + len(call_ids) + 1,)
ids_batch = prefix_ids.unsqueeze(0)  # (1, T_prefix)
```

Do NOT call `collate_fn` directly in generate.py — it requires a response tensor that doesn't exist at inference time.

[VERIFIED: packer.py lines 79–107]

---

## Common Pitfalls

### Pitfall 1: Calling decode_tokens with BOS/SEP/EOS still in the list

**What goes wrong:** decode_tokens validates per-slot ranges. BOS=109, EOS=110, SEP=111 are all above the active vocab range [0..108]. Leaving them in will raise `ValueError` at the time-shift slot validation for the group containing them.

**How to avoid:** Strip before calling: `response_ids = [t for t in generated if t not in (BOS, SEP, EOS)]`

[VERIFIED: decoder.py lines 45–52 — range check `TIME_OFFSET <= t_id < TIME_OFFSET + N_TIME` i.e. 0 <= t_id < 32; BOS=109 fails immediately]

### Pitfall 2: Forgetting model.eval() before generate

**What goes wrong:** TransformerEncoderLayer has dropout=0.0 (so no stochastic issue), but the `enable_nested_tensor=False` fix exists specifically for eval mode. Running inference in train mode causes no correctness issue for this model, but the intent is clear: inference should be in eval mode for conventional correctness and in case dropout is ever added.

**How to avoid:** Always call `model.eval()` and wrap inference in `torch.no_grad()`.

[VERIFIED: transformer.py — enable_nested_tensor=False added specifically for eval mode MPS fix]

### Pitfall 3: mel shape mismatch going into the model

**What goes wrong:** MelExtractor returns `(96, 128)`. ApolloModel.forward expects `(B, 1, 96, 128)`. If you forget either unsqueeze, you get a shape error inside MelEncoder's first Conv2d.

**How to avoid:** `mel.unsqueeze(0).unsqueeze(0)` — add batch dim and channel dim.

[VERIFIED: packer.py line 105 — `torch.stack(mel_list).unsqueeze(1).float()` adds channel dim. For B=1 inference: `mel.unsqueeze(0).unsqueeze(0)` or `mel[None, None, :, :]`]

### Pitfall 4: OneCycleLR step() called per epoch instead of per batch

**What goes wrong:** OneCycleLR is designed to be stepped once per batch (total_steps = n_epochs * steps_per_epoch). Calling step() once per epoch exhausts the schedule in 1/steps_per_epoch of the intended time. Train loss may not converge.

**How to avoid:** train_epoch already calls `scheduler.step()` inside the batch loop (train.py line 119). This is correct. Pass the scheduler to train_epoch and do NOT call scheduler.step() in train.py's outer epoch loop.

[VERIFIED: train.py lines 119 — `if scheduler is not None: scheduler.step()` is inside the batch for-loop]

### Pitfall 5: Sequence length overflow during inference prefix construction

**What goes wrong:** collate_fn enforces `L <= MAX_SEQ_LEN = 64`. During inference, the prefix `[BOS, call_tokens..., SEP]` + generated response tokens must not exceed 64. With D-04 (2–6 call notes × 4 tokens = 8–24 tokens), the prefix is at most 26 tokens. Adding max_tokens=24 response tokens gives 50 total — safely within 64.

**How to avoid:** No action needed for v1 corpus constraints. But if corpus grows (e.g., 6 call notes + 6 response notes = 24+24+3 = 51 tokens), approaching the limit. The model accepts up to max_seq_len=64 token positions in forward(); there's no runtime guard beyond the packer assertion.

[VERIFIED: packer.py line 89 — assertion `L <= MAX_SEQ_LEN`. MAX_SEQ_LEN=64 confirmed]

### Pitfall 6: load_notes does not return BPM

**What goes wrong:** Reading the code superficially, one might assume `load_notes` returns the BPM since it uses `estimate_tempo()` internally. It does not — it only uses BPM for validation. Passing a hardcoded 120.0 to decode_tokens is safe (D-01 constraint), but D-13 says read from the file.

**How to avoid:** Call `pretty_midi.PrettyMIDI(str(call_mid_path)).estimate_tempo()` directly in generate.py to get `call_bpm`.

[VERIFIED: midi.py — no BPM in return value; return is `List[Note]`]

### Pitfall 7: data/pairs/ directory does not exist yet

**What goes wrong:** train.py calls `ingest_corpus` or `discover_pairs` on `data/pairs/`. The directory does not exist in the repo (human authors must populate it). Running train.py on an empty or absent directory will fail with an IngestError.

**How to avoid:** The planner should include a Wave 0 task to `mkdir -p data/pairs/` and document that DATA-05 (≥30 pairs) must be satisfied before running train.py on real data. train.py should print a clear error if the pairs directory is empty or absent.

[VERIFIED: bash output confirmed `data/pairs/` does not yet exist]

---

## Data Directory State

| Path | Status | Note |
|------|--------|------|
| `data/pairs/` | Does not exist | Must be created; human authors populate with ≥30 pairs |
| `data/raw/maestro-v3.0.0/` | Exists | Deprecated corpus (piano/MAESTRO); ignore for this phase |
| `models/` | Exists (gitignored) | Contains smoke checkpoint + deprecated v1–v5 checkpoints |
| `logs/` | Does not exist | Create in train.py if CSV logging is enabled |
| `artifacts/` | May exist | Ingest artifact storage; ingest_corpus CLI defaults to `artifacts/tokenized_v1.pt` |

---

## Corpus Authoring Conventions (DATA-05)

| Convention | Source | Value |
|------------|--------|-------|
| BPM | D-01 | 120 BPM exactly |
| Operator preset variety | D-02 | Vary across pairs (bright plucks, soft pads, percussive FM tones) |
| Key/scale | D-03 | Free choice per pair |
| Gesture length | D-04 | 0.5–1.5s, 2–6 notes per side |
| Response relationship | D-05 | Varied (echo, contrast, continuation); no labeling required |
| Same/different preset per side | D-06 | Free choice |
| File naming | DATA-02 | `data/pairs/NNN/` with `call.mid`, `call.wav`, `response.mid`; NNN zero-padded |
| Minimum pairs | DATA-05 | ≥30 before first real training run |

**Authoring workflow** (human): In Ableton, record call on one MIDI track (Operator), record response on a second MIDI track (same or different Operator preset), bounce call to audio as `call.wav`, export both MIDI tracks as `call.mid` and `response.mid`, drop into `data/pairs/NNN/`.

---

## Training Script Design (train.py)

### CLI Flags (Claude's discretion for most)

| Flag | Type | Default | Source |
|------|------|---------|--------|
| `pairs_root` | positional | — | Required path to data/pairs/ |
| `--epochs` | int | 300 | D-11 |
| `--lr` | float | 1e-3 | Matches train_smoke.py |
| `--batch-size` | int | 4 | Matches train_smoke.py |
| `--log-every` | int | 10 | D-12 |
| `--iteration` | int | 1 | D-10 checkpoint naming |
| `--output-dir` | str | "models" | D-10 |
| `--log-dir` | str | "logs" | D-12 |
| `--seed` | int | 0 | Matches train_smoke.py |
| `--no-csv` | flag | off (CSV enabled) | Claude's discretion |

### Scheduler Construction

```python
# Source: D-09 + train.py train_epoch scheduler plug point
optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)
steps_per_epoch = len(train_loader)
total_steps = args.epochs * steps_per_epoch
scheduler = torch.optim.lr_scheduler.OneCycleLR(
    optimizer,
    max_lr=args.lr,
    total_steps=total_steps,
    pct_start=0.05,
    anneal_strategy="cos",
)
```

### Held-Out Loss Logging

```python
# Called every log_every epochs inside the outer epoch loop
if (epoch + 1) % args.log_every == 0:
    held_loss = _evaluate_heldout_loss(model, held_loader, device)
    print(f"epoch {epoch+1}/{args.epochs}  train_loss={train_loss:.4f}  held_loss={held_loss:.4f}")
    if csv_writer:
        csv_writer.writerow({"epoch": epoch+1, "train_loss": train_loss, "held_loss": held_loss})
```

`_evaluate_heldout_loss` mirrors `_evaluate_type_accuracy` in train_smoke.py but computes `compute_masked_loss` instead.

### Summary Line (per CONTEXT.md specifics)

```
train done: n_pairs=30 split=train/held_out=24/6 epochs=300 final_loss=X.XXXX held_loss=X.XXXX checkpoint=models/run-01-20260520T120000Z.pt
```

---

## Test Infrastructure

### Existing Test Patterns

| File | Pattern | Relevant for Phase 3 |
|------|---------|---------------------|
| `test_smoke_train.py` | End-to-end integration test: calls main(), checks type_accuracy gate, wall-clock | Template for `test_train.py` (real training) and `test_generate.py` |
| `test_checkpoint.py` | Contract tests on 5-key format; round-trip reconstruction | generate.py test must verify checkpoint loading and model reconstruction |
| `test_train.py` | TDD RED-GREEN unit tests for loss mask, metrics, train_epoch | Shows exact fixture pattern with mock_artifact |
| `test_packer.py` | Layout tests, pad mask correctness | Reference for inference sequence construction tests |

### Test Fixture Pattern (from test_train.py)

```python
@pytest.fixture(scope="module")
def mock_artifact(tmp_path_factory):
    from apollo.ingest.mock import synthesize_pair
    from apollo.ingest.artifact import ingest
    root = tmp_path_factory.mktemp("pairs")
    for i in range(6):
        synthesize_pair(root, nnn=f"{i:03d}")
    synthesize_pair(root, nnn="006")  # heldout
    return ingest(root)
```

### New Test Files Needed

| File | Tests |
|------|-------|
| `tests/test_generate.py` | Smoke test: mock pair → generate.py → response_001.mid exists, valid MIDI, ≥1 note; invalid token skip; N-sample output naming |
| `tests/test_train.py` (extend) | Or new `tests/test_train_real.py`: train.py CLI smoke on mock pairs, held-out logging, checkpoint naming convention |

[VERIFIED: tests/ directory listing — these files do not yet exist]

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| MPS (Apple Silicon) | Training, inference | Confirmed | PyTorch 2.x | CPU (auto via get_device()) |
| pretty_midi | generate.py MIDI write | Confirmed | 0.2.11 | None — required |
| torchaudio | MelExtractor | Confirmed | 2.x | None — required |
| torch.optim.lr_scheduler.OneCycleLR | train.py | Confirmed | stdlib PyTorch | None — required |

[VERIFIED: train_smoke.py, ingest.py, audio.py all import successfully; 100/100 tests pass]

**Step 2.6: SKIPPED for corpus authoring task (no external dependencies beyond Ableton, which is a human tool). Environment confirmed adequate for all code tasks.**

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The inference prefix should be `[BOS, call_tokens..., SEP]` (not just `[BOS]`) to condition the model on call token structure as well as mel conditioning | Sampling Loop Detail | Model may generate contextually disconnected responses if prefix is wrong. However, this matches training layout exactly, so risk is LOW. |
| A2 | `pretty_midi.PrettyMIDI(mid_path).estimate_tempo()` is the correct API to extract BPM for decode_tokens | API Contracts | If estimate_tempo returns a wrong value for valid 120 BPM MIDI, timing will be off. Risk is LOW — validated by load_notes in Phase 1. |

Both assumptions are HIGH confidence. A1 is derived directly from packer.py training layout; A2 is verified by existing load_notes code.

---

## Open Questions

1. **Should generate.py also encode the call via Tokenizer.encode and include call tokens in the prefix, or is the mel-only prefix sufficient?**
   - What we know: training always has `[BOS, call_tokens, SEP, response_tokens, EOS]`. The model learned to produce response tokens after seeing both the mel conditioning AND the call token sequence.
   - What's unclear: whether using only `[BOS, SEP]` as prefix (mel only) would produce reasonable output, or if call tokens in the prefix are needed.
   - Recommendation: Use `[BOS, call_tokens..., SEP]` prefix — matches training distribution exactly and requires no new design decision. This requires generate.py to also run Tokenizer.encode on call.mid notes.

2. **What does train.py do if data/pairs/ has fewer than 30 pairs?**
   - Recommendation: Print a warning but continue training. The 30-pair requirement (DATA-05) is a human authoring gate, not a code hard-stop. train.py should warn if n_pairs < 30 but not abort.

---

## Sources

### Primary (HIGH confidence — verified against live source code)
- `apollo/tokenizer/decoder.py` — decode_tokens API, range validation, partial group drop behavior
- `apollo/tokenizer/vocab.py` — Token ID layout: BOS=109, EOS=110, SEP=111, active vocab [0..111]
- `apollo/model/transformer.py` — ApolloModel.forward signature: (B,T) int64, (B,1,96,128) float32, (B,T) bool → (B,T,256)
- `apollo/model/train.py` — train_epoch scheduler plug (line 119), load_checkpoint API
- `apollo/model/packer.py` — collate_fn sequence layout, PAD_ID=0, MAX_SEQ_LEN=64
- `apollo/model/__init__.py` — full re-export list for Phase 3 imports
- `apollo/ingest/midi.py` — load_notes does NOT return BPM (confirmed by signature + body scan)
- `apollo/ingest/audio.py` — MelExtractor returns (96, 128) float32
- `apollo/ingest/mock.py` — synthesize_pair API for test fixtures
- `apollo/scripts/train_smoke.py` — CLI structure template for train.py
- `tests/test_train.py`, `tests/test_packer.py`, `tests/test_smoke_train.py` — test fixture and assertion patterns
- `.planning/phases/02-model-training/02-05-SUMMARY.md` — checkpoint 5-key format confirmed
- `.planning/phases/02-model-training/02-02-SUMMARY.md` — ApolloModel.forward contract confirmed
- `.planning/phases/03-corpus-inference/03-CONTEXT.md` — all locked decisions

### Secondary (MEDIUM confidence)
- `torch.optim.lr_scheduler.OneCycleLR` per-step calling convention [ASSUMED based on PyTorch standard usage; verified consistent with train_epoch's scheduler.step() placement]

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries verified in live imports
- API contracts: HIGH — all verified against live source code with line numbers
- Architecture patterns: HIGH — derived from verified source; one LOW-risk inference prefix assumption noted
- Pitfalls: HIGH — each pitfall traced to specific source file location
- Test patterns: HIGH — verified against existing test files

**Research date:** 2026-05-19
**Valid until:** Stable — no external dependencies introduced; only invalidated by source file changes within this repo

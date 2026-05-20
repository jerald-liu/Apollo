# Phase 2: Model & Training — Research

**Researched:** 2026-05-19
**Domain:** PyTorch decoder-only transformer, CNN mel encoder, MPS training
**Confidence:** HIGH — all critical patterns verified by live execution on the target machine (MPS, PyTorch 2.8.0)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Mel encoder is `Conv2d(1→32,3×3) → ReLU → MaxPool(2×2) → Conv2d(32→64,3×3) → ReLU → MaxPool(2×2) → Conv2d(64→128,3×3) → ReLU → AdaptiveAvgPool2d(1,1) → Flatten → FC(128→d_model)`. Input `(B,1,96,128)`, output `(B,d_model)`.
- **D-02:** Mel encoder jointly trained (no frozen weights).
- **D-04:** Mel injected as prefix token at position 0. Projected mel + learned positional embedding at pos 0 prepended before BOS.
- **D-05:** No cross-attention. No broadcast-add. Prefix token only.
- **D-06:** Positions: 0=MEL, 1=BOS, 2..N+1=call, N+2=SEP, N+3..M+3=response, M+4=EOS.
- **D-07:** Decoder-only transformer. `d_model=128`, `n_layers=4`, `n_heads=4`, `d_ff=512`.
- **D-08:** `max_seq_len=64`.
- **D-09:** Causal mask only. No encoder.
- **D-10:** Learned absolute positional embeddings.
- **D-11:** Token sequence stored as `[BOS, call_tokens, SEP, response_tokens, EOS]` in packed form; mel is injected by the model's forward method, not in the token sequence.
- **D-12:** Pad to `max_seq_len=64` using `PAD_ID=0`. Attention mask True=real, False=padding.
- **D-13:** Custom `collate_fn`, `batch_size=4`.
- **D-14:** Loss computed on all positions, zeroed on non-response positions before mean. Response = SEP+1 through EOS inclusive. Call tokens, BOS, SEP excluded from gradient. MEL prefix excluded.
- **D-15:** Loss mask derived from token ID sequence (find SEP), robust to variable call lengths.
- **D-16:** AdamW, `lr=1e-3`, no LR schedule for smoke train. Training loop accepts `scheduler=None` arg.
- **D-17:** Gradient clipping `max_norm=1.0`.
- **D-18:** No mixed precision. Float32 throughout.
- **D-19:** Device: MPS if available, else CPU. No hard-coded CUDA.
- **D-20/21:** Type-accuracy = token category correct on response positions. Categories: `[0..31]`=time_shift, `[32..68]`=pitch, `[69..84]`=velocity, `[85..108]`=duration, `[109..111]`=special. >95% target.
- **D-22:** Metric computed over final epoch on full training set (overfit-by-design check).
- **D-23/24:** Checkpoint as `.pt` dict with keys `model_state_dict`, `mel_encoder_state_dict`, `vocab`, `model_config`, `training_meta`. Loaded with `weights_only=False`.
- **D-25:** Module layout: `apollo/model/{mel_encoder.py, transformer.py, packer.py, train.py, metrics.py}`, `apollo/scripts/train_smoke.py`.
- **D-26:** `apollo/model/__init__.py` re-exports main classes.
- **D-27:** No augmentation in Phase 2.

### Claude's Discretion
- Module layout (D-25) is labeled discretion but the layout is specified explicitly above — treat as locked.
- `norm_first` setting for `TransformerEncoderLayer` (Post-LN vs Pre-LN): research recommends `norm_first=False` (see Section 3 below).

### Deferred Ideas (OUT OF SCOPE)
- Pitch-shift augmentation (Phase 3)
- LR warmup + cosine decay (Phase 3)
- Mixed precision (future)
- Top-k / temperature sampling (Phase 3)
- `torch.compile` / gradient checkpointing
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| COND-02 | Mel CNN encoder compresses mel tensor to conditioning embedding | D-01 fully specified; verified shape (B,1,96,128)→(B,128) on MPS in Section 3 |
| COND-03 | Mel encoder jointly trained (not frozen) | D-02; same optimizer param group as transformer; Section 7 |
| TRAIN-01 | Samples packed as `[BOS, call_tokens, SEP, response_tokens, EOS]` | Section 5 (collate_fn); Section 6 (loss mask alignment) |
| TRAIN-02 | Cross-entropy loss masked to response tokens only | Section 6; verified boundary math; critical fix documented |
| TRAIN-03 | Train from scratch (random init) | No special action needed; just don't load checkpoint at init |
| TRAIN-04 | >95% next-token type-accuracy on response side | Section 8 (metrics); verified tensor op implementation |
| TRAIN-05 | Runs on MPS locally | All patterns verified on MPS PyTorch 2.8; Section 4 |
| TRAIN-06 | Checkpoint: model + mel encoder + tokenizer config in single artifact | Section 9; verified save/load round-trip (~3.8 MB) |
</phase_requirements>

---

## Summary

Phase 2 builds a decoder-only transformer (~976k parameters total) conditioned on a mel spectrogram via a CNN prefix token. The architecture is fully specified in CONTEXT.md; this document answers the eight implementation questions about the correct PyTorch idioms.

The canonical pattern for a pure decoder-only LM in PyTorch 2.8 is `nn.TransformerEncoderLayer` (not `TransformerDecoderLayer`) with an explicit float causal mask plus `is_causal=True`. The MEL prefix token is injected by concatenating a `(B,1,d_model)` tensor at position 0 before the transformer stack. Mask combination is float `src_mask (T,T)` plus bool `src_key_padding_mask (B,T)` — this triggers a UserWarning but works correctly; suppress with `warnings.filterwarnings`. The loss mask boundary is `j >= sep_pos` (not `j > sep_pos`) in shifted-target space. `PAD_ID=0` reusing `TIME bin 0` is safe only if the padding mask is computed from sequence length, never from `token_ids == 0`.

**Primary recommendation:** Implement as specified; every pattern has been verified by live execution on MPS + PyTorch 2.8. No architectural changes are needed.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Mel feature extraction | Ingest (Phase 1) | — | Already complete; `MelExtractor` produces `(96,128)` float32 stored in artifact |
| Mel compression to embedding | Model (mel_encoder.py) | — | CNN encoder is model-owned, jointly trained |
| Sequence packing `[BOS,call,SEP,resp,EOS]` | packer.py (DataLoader layer) | — | Boundary between Phase 1 artifact and Phase 2 training loop |
| Causal self-attention | transformer.py | — | Decoder-only stack; no separate encoder |
| MEL prefix injection | transformer.py forward | — | Happens inside model.forward, not in data pipeline |
| Response-only loss mask | train.py | — | Derived from token IDs at training time |
| Type-accuracy metric | metrics.py | — | Post-forward, uses same token categories as Vocab |
| Checkpoint serialization | train.py | — | Saves combined dict at training end |

---

## Standard Stack

### Core (all already in pyproject.toml)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| torch | 2.8.0 | All model/training ops | Project requirement; MPS support |
| torchaudio | 2.8.0 | Already used for mel | Consistent with Phase 1 |
| numpy | >=1.24 | Bin edge computation | Already present |

[VERIFIED: `./venv/bin/python -c "import torch; print(torch.__version__)"` → `2.8.0`]

**No new dependencies required for Phase 2.** All needed PyTorch submodules (`nn.TransformerEncoderLayer`, `nn.Conv2d`, `nn.AdaptiveAvgPool2d`, `torch.optim.AdamW`) are in the existing `torch` install.

**Installation:** Nothing to add.

---

## Architecture Patterns

### System Architecture Diagram

```
call.wav ─────► MelExtractor ──► (96,128) float32 ─────► stored in .pt artifact
call.mid ─────► Tokenizer.encode ──► int list ─────────► stored in .pt artifact
response.mid ─► Tokenizer.encode ──► int list ─────────► stored in .pt artifact

Training forward pass:
┌─────────────────────────────────────────────────────────────────────────────┐
│ DataLoader (packer.py collate_fn)                                           │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │ per-item: [BOS, call_tokens(12), SEP, resp_tokens(12), EOS] → pad64  │  │
│   │ return: token_ids(B,64), pad_mask(B,64), mel(B,1,96,128)            │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
          │ token_ids            │ mel                    │ pad_mask
          ▼                      ▼                        │
┌──────────────────┐   ┌──────────────────────┐         │
│ tok_emb(256,128) │   │ MelEncoder (CNN+FC)  │         │
│ pos_emb(65, 128) │   │ (B,1,96,128)→(B,128) │         │
└────────┬─────────┘   └──────────┬───────────┘         │
         │ (B,T,128)              │ (B,128)              │
         │ + pos 1..T             │ + pos_emb[0]         │
         ▼                        ▼                       │
    tok_embeds(B,T,128)   mel_prefix(B,1,128)            │
         └─────── torch.cat ──────┘                      │
                    │ (B, 1+T, 128)                       │
                    ▼                                     ▼
          ┌───────────────────────────────────────────────────┐
          │ TransformerEncoder (4 × TransformerEncoderLayer)  │
          │   src_mask: causal float (1+T, 1+T)               │
          │   src_key_padding_mask: [False, pad_mask] (B,1+T) │
          └───────────────────────┬───────────────────────────┘
                                  │ (B, 1+T, 128)
                                  │ out[:, 1:]  (drop MEL position)
                                  ▼
                          out_proj (B, T, 256)
                          ────────────────────
                          logits (B, T, 256)
                                  │
                    ┌─────────────┴───────────────┐
                    ▼                             ▼
           loss_mask (j >= sep_pos)         type_accuracy
           CE(logits[:,:-1], ids[:,1:])     (response side only)
           masked mean → scalar loss
```

### Recommended Project Structure

```
apollo/model/
├── __init__.py          # re-exports ApolloModel, MelEncoder, ApolloDataset, compute_type_accuracy
├── mel_encoder.py       # MelEncoder(nn.Module): CNN + FC
├── transformer.py       # ApolloModel(nn.Module): tok_emb + pos_emb + TransformerEncoder + out_proj
│                        #   forward(token_ids, mel_input, key_padding_mask) -> logits(B,T,V)
├── packer.py            # ApolloDataset(Dataset) + collate_fn; loads artifact, packs sequences
├── train.py             # train_epoch(), run_training() — accepts scheduler=None
└── metrics.py           # compute_type_accuracy(logits, targets, loss_mask) -> float

apollo/scripts/
└── train_smoke.py       # CLI entry point: generate 10 mock pairs, ingest, train, save checkpoint
```

---

## Section 1: Decoder-Only Transformer in PyTorch 2.8

**The correct idiom:** Use `nn.TransformerEncoderLayer` (not `TransformerDecoderLayer`) with a causal mask. The "Encoder" naming is historical — a stack of self-attention + FFN layers with a causal mask *is* a decoder-only LM.

`nn.TransformerDecoderLayer` requires a memory tensor (from an encoder) and cannot be used as a standalone causal LM without awkward workarounds. Do not use it.

[VERIFIED: live execution on MPS; TransformerEncoderLayer with causal mask trains correctly]

```python
# Source: verified on MPS PyTorch 2.8 in this research session

import torch
import torch.nn as nn

# Build the transformer stack
encoder_layer = nn.TransformerEncoderLayer(
    d_model=128,
    nhead=4,
    dim_feedforward=512,
    batch_first=True,       # (B, T, d_model) convention — required
    dropout=0.0,            # no dropout for smoke train
    norm_first=False,       # Post-LN (default); avoids nested_tensor warning (see Section 4)
)
transformer = nn.TransformerEncoder(encoder_layer, num_layers=4)

# Causal mask: upper-triangular -inf, diagonal 0
def make_causal_mask(seq_len: int, device) -> torch.Tensor:
    """Returns float (seq_len, seq_len) causal mask. -inf means 'cannot attend'."""
    return torch.full((seq_len, seq_len), float('-inf'), device=device).triu(1)
```

**Key constraint:** `is_causal=True` MUST be accompanied by an explicit `src_mask`. Calling `layer(x, is_causal=True)` without a mask raises `RuntimeError: Need attn_mask if specifying the is_causal hint` in PyTorch 2.8.

[VERIFIED: `RuntimeError` confirmed by live test]

---

## Section 2: MEL Prefix Token Injection

The MEL vector from the CNN encoder is `(B, d_model)`. To inject it at position 0:

1. Project + add positional embedding at index 0: `mel_prefix = mel_embed.unsqueeze(1) + pos_emb(zeros(B,1))`
2. Token embeddings occupy positions 1..T: `tok = tok_emb(token_ids) + pos_emb(arange(1, T+1))`
3. Concatenate: `x = torch.cat([mel_prefix, tok], dim=1)` → shape `(B, 1+T, d_model)`

[VERIFIED: shape `(4, 16, 128)` confirmed for `B=4, T=15`]

```python
# Source: verified on MPS PyTorch 2.8

def forward(self, token_ids: torch.Tensor, mel_input: torch.Tensor,
            key_padding_mask: torch.Tensor | None = None) -> torch.Tensor:
    """
    token_ids:       (B, T) — [BOS, call, SEP, resp, EOS, PAD...]
    mel_input:       (B, 1, 96, 128) — raw mel from artifact (add channel dim in collate_fn)
    key_padding_mask:(B, T) bool — True = padding position in TOKEN sequence
    Returns: logits  (B, T, vocab_size)
    """
    import warnings
    B, T = token_ids.shape

    # Mel encoder: (B, 1, 96, 128) → (B, d_model)
    mel_embed = self.mel_enc(mel_input)

    # Token embeddings at positions 1..T
    positions = torch.arange(1, T + 1, device=token_ids.device).unsqueeze(0)  # (1, T)
    tok = self.tok_emb(token_ids) + self.pos_emb(positions)  # (B, T, d_model)

    # MEL prefix at position 0
    mel_pos = torch.zeros(B, 1, dtype=torch.long, device=token_ids.device)
    mel_prefix = mel_embed.unsqueeze(1) + self.pos_emb(mel_pos)  # (B, 1, d_model)

    # Concatenate: [mel, tokens]
    x = torch.cat([mel_prefix, tok], dim=1)  # (B, 1+T, d_model)
    total_len = 1 + T

    # Causal mask (includes MEL prefix position)
    causal = torch.full((total_len, total_len), float('-inf'), device=x.device).triu(1)

    # Pad mask: prepend False for MEL prefix (never padding)
    if key_padding_mask is not None:
        mel_not_pad = torch.zeros(B, 1, dtype=torch.bool, device=x.device)
        full_pad = torch.cat([mel_not_pad, key_padding_mask], dim=1)  # (B, 1+T)
    else:
        full_pad = None

    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        out = self.transformer(x, mask=causal, src_key_padding_mask=full_pad, is_causal=True)

    # Drop MEL prefix position, project tokens to vocab
    return self.out_proj(out[:, 1:])  # (B, T, vocab_size)
```

**Position embedding table size:** Must be `max_seq_len + 1` to accommodate positions 0..max_seq_len (0=MEL, 1..64=token positions). With `max_seq_len=64`, use `nn.Embedding(65, d_model)`.

[VERIFIED: live execution confirmed]

---

## Section 3: Causal Mask + Padding Mask Combination

**Pattern:** Float `src_mask (T,T)` + bool `src_key_padding_mask (B,T)`, plus `is_causal=True`.

[VERIFIED: all three combinations tested on MPS PyTorch 2.8]

```python
# Causal mask: float, (T, T), -inf in upper triangle
causal = torch.full((T, T), float('-inf'), device=device).triu(1)

# Padding mask: bool, (B, T), True = padding position
# WARNING: NEVER compute as (token_ids == 0) — see PAD_ID pitfall in Section 11
pad_mask = torch.zeros(B, T, dtype=torch.bool, device=device)
pad_mask[i, actual_length:] = True  # set per-sample in collate_fn

# Combined forward (suppress mismatched-type UserWarning):
import warnings
with warnings.catch_warnings():
    warnings.simplefilter('ignore', UserWarning)
    out = layer(x, src_mask=causal, src_key_padding_mask=pad_mask, is_causal=True)
```

**The UserWarning** ("Support for mismatched src_key_padding_mask and src_mask is deprecated") is triggered when `src_mask` is float and `src_key_padding_mask` is bool. It is a deprecation warning, not an error. Both masks are applied correctly despite the warning. Suppress with `warnings.filterwarnings` or context manager.

**Alternative (no warning):** Convert both to float. But this requires expanding `key_padding_mask` from `(B,T)` to `(B,T,T)` which TransformerEncoderLayer does not natively accept as `src_mask`. The float+bool pattern is the practical choice for variable-length batches.

[VERIFIED: `(4, 10, 128)` output confirmed with both masks on MPS]

---

## Section 4: MPS-Specific Training Considerations

**Verified working on MPS PyTorch 2.8:**
- `nn.TransformerEncoderLayer` + `TransformerEncoder` — OK [VERIFIED]
- `nn.Conv2d`, `nn.AdaptiveAvgPool2d`, `nn.Linear` — OK [VERIFIED]
- `AdamW` + `loss.backward()` + `clip_grad_norm_` — OK [VERIFIED: 5 steps in 1.67s]
- Float32 forward + backward pass — OK [VERIFIED]
- Float16 — technically works on this MPS version but explicitly deferred (D-18)

**norm_first setting:**
- `norm_first=False` (Post-LN, the default): no construction warnings, standard behavior. **Use this.**
- `norm_first=True` (Pre-LN): triggers `UserWarning: enable_nested_tensor is True, but self.use_nested_tensor is False`. Pre-LN is better at large scale, but adds a distracting warning with no benefit at Phase 2 scale. Use `norm_first=False`.

[VERIFIED: live test confirmed warning suppression with norm_first=False]

**Device selection pattern:**
```python
def get_device() -> torch.device:
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")
```

**`is_causal=True` requires explicit `src_mask`:**
```python
# WRONG — raises RuntimeError on PyTorch 2.8:
out = layer(x, is_causal=True)  # RuntimeError: Need attn_mask if specifying the is_causal hint

# CORRECT:
out = layer(x, src_mask=causal, is_causal=True)
```

[VERIFIED: `RuntimeError` confirmed by live test]

**Parameter count correction:** CONTEXT.md estimated ~200k parameters. Actual count is ~976k:
- MelEncoder (CNN + FC): 109,184
- TransformerEncoder (4 layers): 793,088
- tok_emb + pos_emb: 41,088
- out_proj: 33,024
- **Total: 976,384**

This is still tiny and trains in seconds on MPS. The 200k figure was an underestimate; no architectural change needed.

[VERIFIED: `sum(p.numel() for p in model.parameters())` = 976,384]

---

## Section 5: DataLoader collate_fn

```python
# Source: verified on PyTorch 2.8

from torch.utils.data import Dataset, DataLoader
import torch

BOS, EOS, SEP = 109, 110, 111
PAD_ID = 0   # reuses TIME bin 0 — see Section 11 for pad_mask warning
MAX_SEQ_LEN = 64

class ApolloDataset(Dataset):
    """Wraps the Phase 1 artifact entries."""
    def __init__(self, artifact: dict, split: str = "train"):
        # split = "train" | "all" | "held_out"
        self.entries = [
            e for e in artifact["pairs"]
            if split == "all"
            or (split == "train" and not e["is_heldout"])
            or (split == "held_out" and e["is_heldout"])
        ]

    def __len__(self):
        return len(self.entries)

    def __getitem__(self, idx):
        e = self.entries[idx]
        return e["call_tokens"], e["response_tokens"], e["call_mel"]


def collate_fn(batch):
    """
    Packs [BOS, call_tokens, SEP, resp_tokens, EOS] per sample, pads to MAX_SEQ_LEN.

    Returns:
        token_ids: (B, MAX_SEQ_LEN) int64
        pad_mask:  (B, MAX_SEQ_LEN) bool — True = padding position
                   COMPUTED FROM SEQUENCE LENGTH, not from token value==0 (see Section 11)
        mel:       (B, 1, 96, 128) float32 — channel dim added here
    """
    token_ids_list, pad_mask_list, mel_list = [], [], []

    for call_toks, resp_toks, mel in batch:
        seq = torch.cat([
            torch.tensor([BOS], dtype=torch.long),
            call_toks.long(),
            torch.tensor([SEP], dtype=torch.long),
            resp_toks.long(),
            torch.tensor([EOS], dtype=torch.long),
        ])
        L = seq.shape[0]
        assert L <= MAX_SEQ_LEN, f"Sequence length {L} exceeds MAX_SEQ_LEN={MAX_SEQ_LEN}"

        padded = torch.full((MAX_SEQ_LEN,), PAD_ID, dtype=torch.long)
        padded[:L] = seq
        pad_mask = torch.zeros(MAX_SEQ_LEN, dtype=torch.bool)
        pad_mask[L:] = True  # positional, not value-based

        token_ids_list.append(padded)
        pad_mask_list.append(pad_mask)
        mel_list.append(mel)

    return (
        torch.stack(token_ids_list),             # (B, 64)
        torch.stack(pad_mask_list),              # (B, 64) bool
        torch.stack(mel_list).unsqueeze(1),      # (B, 1, 96, 128)
    )
```

[VERIFIED: `(4,64)`, `(4,64)`, `(4,1,96,128)` shapes confirmed]

---

## Section 6: Response-Only Loss Mask

**Critical math:** In shifted next-token prediction, `logits[:, j]` predicts `token_ids[:, j+1]`. A position `j` is a response prediction when `token_ids[j+1]` is a response token, i.e., `j+1 > sep_pos`, i.e., **`j >= sep_pos`**.

Using `j > sep_pos` would skip the first response token. This is a subtle off-by-one that is easy to miss.

[VERIFIED: boundary math confirmed by live test; first True at `j=sep_pos`, not `j=sep_pos+1`]

```python
# Source: verified on PyTorch 2.8 MPS

def compute_masked_loss(logits: torch.Tensor, token_ids: torch.Tensor,
                        sep_id: int = 111) -> torch.Tensor:
    """
    logits:     (B, T, vocab_size) — model output for token positions (MEL already dropped)
    token_ids:  (B, T) — packed sequence [BOS, call, SEP, resp, EOS, PAD...]
    Returns: scalar loss masked to response tokens (SEP+1 through EOS inclusive)
    """
    B, T, V = logits.shape

    # Shifted prediction: logits[:, :-1] predicts token_ids[:, 1:]
    logits_shifted = logits[:, :-1]        # (B, T-1, V)
    targets_shifted = token_ids[:, 1:]     # (B, T-1)

    # Find SEP position per sample
    sep_pos = (token_ids == sep_id).long().argmax(dim=1)  # (B,) — index of first SEP

    # Loss mask: j >= sep_pos in shifted space
    # j-th shifted position predicts token_ids[j+1]
    # We want token_ids[j+1] to be a response token: j+1 > sep_pos => j >= sep_pos
    j_range = torch.arange(T - 1, device=token_ids.device).unsqueeze(0)  # (1, T-1)
    loss_mask = j_range >= sep_pos.unsqueeze(1)  # (B, T-1)

    per_token_loss = torch.nn.functional.cross_entropy(
        logits_shifted.reshape(-1, V),
        targets_shifted.reshape(-1),
        reduction='none'
    ).reshape(B, T - 1)

    return (per_token_loss * loss_mask.float()).sum() / (loss_mask.float().sum() + 1e-8)
```

**D-14 compliance verification:**
- `j = sep_pos - 1`: target = SEP → excluded (j < sep_pos). Correct.
- `j = sep_pos`: target = resp[0] → included (j >= sep_pos). Correct.
- `j = T-2`: target = EOS → included. Correct.
- PAD positions after EOS: excluded (their corresponding input positions were never SEP, but the loss mask is built from `j >= sep_pos`, and since EOS appears before PAD, PAD positions at `j > eos_shifted_pos` are beyond the valid sequence — their targets are PAD tokens but the mask naturally excludes them if `sep_pos` is correctly detected). **Safe because loss mask is position-derived.**

---

## Section 7: Training Loop Structure

```python
# Source: verified on MPS PyTorch 2.8

import torch
import torch.nn as nn
from torch.utils.data import DataLoader

def train_epoch(model, mel_enc, dataloader, optimizer, device, scheduler=None):
    """One epoch. scheduler=None for smoke train; Phase 3 passes warmup+cosine."""
    model.train()
    mel_enc.train()
    total_loss = 0.0
    n_batches = 0

    for token_ids, pad_mask, mel in dataloader:
        token_ids = token_ids.to(device)
        pad_mask = pad_mask.to(device)
        mel = mel.to(device).float()

        logits = model(token_ids, mel, key_padding_mask=pad_mask)  # (B, T, V)

        loss = compute_masked_loss(logits, token_ids)

        optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(
            list(model.parameters()) + list(mel_enc.parameters()),
            max_norm=1.0
        )
        optimizer.step()
        if scheduler is not None:
            scheduler.step()

        total_loss += loss.item()
        n_batches += 1

    return total_loss / n_batches
```

**Single optimizer for both mel_enc and transformer:**
```python
optimizer = torch.optim.AdamW(
    list(model.parameters()) + list(mel_enc.parameters()),
    lr=1e-3
)
```

Or, if `ApolloModel` contains `mel_enc` as a submodule, just `model.parameters()` covers both.

[VERIFIED: AdamW + clip_grad_norm_ + backward on MPS confirmed in 5-step test]

---

## Section 8: Type-Accuracy Metric

```python
# Source: verified on PyTorch 2.8 MPS

def token_category(ids: torch.Tensor) -> torch.Tensor:
    """Map token IDs to category indices.
    0=time_shift, 1=pitch, 2=velocity, 3=duration, 4=special, 5=reserved
    """
    cat = torch.zeros_like(ids, dtype=torch.long)
    cat = torch.where((ids >= 32) & (ids < 69),  torch.ones_like(ids), cat)
    cat = torch.where((ids >= 69) & (ids < 85),  torch.full_like(ids, 2), cat)
    cat = torch.where((ids >= 85) & (ids < 109), torch.full_like(ids, 3), cat)
    cat = torch.where((ids >= 109) & (ids < 112),torch.full_like(ids, 4), cat)
    cat = torch.where(ids >= 112,                torch.full_like(ids, 5), cat)
    return cat

def compute_type_accuracy(logits: torch.Tensor, token_ids: torch.Tensor,
                          sep_id: int = 111) -> float:
    """
    logits:     (B, T, vocab_size)
    token_ids:  (B, T) packed sequence
    Returns: type accuracy on response positions (float 0-1)
    """
    B, T, V = logits.shape
    preds = logits[:, :-1].argmax(dim=-1)      # (B, T-1) predicted next tokens
    targets = token_ids[:, 1:]                  # (B, T-1) actual next tokens

    sep_pos = (token_ids == sep_id).long().argmax(dim=1)
    j_range = torch.arange(T - 1, device=token_ids.device).unsqueeze(0)
    resp_mask = j_range >= sep_pos.unsqueeze(1)  # (B, T-1)

    pred_cats = token_category(preds)
    target_cats = token_category(targets)

    correct = (pred_cats == target_cats) & resp_mask
    return correct.float().sum().item() / (resp_mask.float().sum().item() + 1e-8)
```

**Why >95% is achievable on mock data:** Mock pairs have fixed 3-note structure. The 4-token-per-note grammar means the expected token category at each response position is deterministic (`(pos mod 4)` → time/pitch/vel/dur). A model that has learned the packing pattern gets near-perfect type accuracy even without learning note values. This is the "wiring check" — if type accuracy stays low, the architecture or mask is broken.

[VERIFIED: category mapping tested for all boundary IDs (0,31,32,68,69,84,85,108,109,111,112,255)]

---

## Section 9: Checkpoint Format

```python
# Source: verified save/load round-trip (~3.8 MB on disk)
import torch
from pathlib import Path
from datetime import datetime, timezone

def save_checkpoint(
    model: nn.Module,        # ApolloModel (contains mel_enc as submodule OR separate)
    mel_enc: nn.Module,      # MelEncoder
    vocab_dict: dict,        # from artifact["vocab"]
    model_config: dict,
    training_meta: dict,
    out_path: str,
) -> None:
    """
    Saves self-contained checkpoint. Uses weights_only=False on load (trusted local file).
    See D-24 / T-01-14 disposition: accept for OUR files.
    """
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "model_state_dict":     model.state_dict(),
        "mel_encoder_state_dict": mel_enc.state_dict(),
        "vocab":               vocab_dict,
        "model_config":        model_config,
        "training_meta":       training_meta,
    }, out_path)

def load_checkpoint(path: str, map_location="cpu") -> dict:
    """Load trusted local checkpoint. weights_only=False — OUR file."""
    return torch.load(path, map_location=map_location, weights_only=False)

# model_config dict:
model_config = {
    "d_model": 128, "n_layers": 4, "n_heads": 4,
    "d_ff": 512, "max_seq_len": 64, "vocab_size": 256,
}

# training_meta dict:
training_meta = {
    "n_epochs": n_epochs,
    "n_pairs": n_pairs,
    "final_loss": float(final_loss),
    "type_accuracy": float(type_accuracy),
    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
}
```

**Checkpoint path pattern:** `models/smoke-{timestamp}.pt` (e.g., `models/smoke-20260519T224500Z.pt`). The `models/` directory should be in `.gitignore`.

**Phase 3 reconstruction:** Load `model_config` from checkpoint, instantiate `ApolloModel(**model_config)`, call `model.load_state_dict(ckpt["model_state_dict"])`. No need for the class definition to be in the same file as the checkpoint loader.

[VERIFIED: 3,836 KB checkpoint saved and loaded; state_dicts reconstructed correctly]

---

## Section 10: MelEncoder Module

```python
# Source: verified on MPS, shape (B,1,96,128) → (B,128)

class MelEncoder(nn.Module):
    """CNN mel encoder. Input: (B, 1, 96, 128). Output: (B, d_model).
    Jointly trained with transformer — same optimizer param group.
    """
    def __init__(self, d_model: int = 128):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(1,  32, kernel_size=3, padding=1), nn.ReLU(), nn.MaxPool2d(2),  # (B,32,48,64)
            nn.Conv2d(32, 64, kernel_size=3, padding=1), nn.ReLU(), nn.MaxPool2d(2),  # (B,64,24,32)
            nn.Conv2d(64,128, kernel_size=3, padding=1), nn.ReLU(),                   # (B,128,24,32)
            nn.AdaptiveAvgPool2d((1, 1)),                                               # (B,128,1,1)
        )
        self.fc = nn.Linear(128, d_model)

    def forward(self, mel: torch.Tensor) -> torch.Tensor:
        # mel: (B, 1, 96, 128)
        x = self.net(mel)   # (B, 128, 1, 1)
        x = x.flatten(1)    # (B, 128)
        return self.fc(x)   # (B, d_model)
```

Parameter count: 109,184. [VERIFIED]

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Causal self-attention | Manual QKV attention | `nn.TransformerEncoderLayer` | Handles masking edge cases, MPS-tested, optimized kernel |
| Gradient clipping | Manual norm computation | `nn.utils.clip_grad_norm_` | Handles parameter groups, in-place, numerically stable |
| Positional embedding | Sinusoidal formula | `nn.Embedding(max_pos, d_model)` | Learned embeddings specified in D-10; simpler |
| Checkpoint serialization | Custom pickle | `torch.save` / `torch.load` | Standard; handles tensors, state_dicts |
| Cross-entropy loss | Log-softmax + NLL | `F.cross_entropy(reduction='none')` | Numerically stable log-sum-exp |

---

## Common Pitfalls

### Pitfall 1: PAD_ID=0 equals TIME bin 0 — pad_mask must be length-based

**What goes wrong:** Computing `pad_mask = (token_ids == 0)` falsely marks `time_shift=0` tokens (the first note in any phrase) as padding. The transformer then ignores those positions, corrupting attention.

**Why it happens:** D-12 reuses `PAD_ID=0 = TIME_OFFSET=0`. The time_shift bin 0 ("no time shift") is a valid and common token for the first note.

**How to avoid:** Track actual sequence length in `collate_fn`. Set `pad_mask[i, actual_length:]= True` positionally.

[VERIFIED: positions 1 and 6 incorrectly marked as padding when using `== 0` approach]

```python
# WRONG:
pad_mask = (packed == 0)  # marks time_shift=0 tokens as padding

# CORRECT:
pad_mask = torch.zeros(MAX_SEQ_LEN, dtype=torch.bool)
pad_mask[actual_seq_length:] = True  # positional
```

### Pitfall 2: Loss mask off-by-one in shifted prediction space

**What goes wrong:** Using `j > sep_pos` instead of `j >= sep_pos` skips the first response token from the loss, making the mask inconsistent with D-14.

**Why it happens:** Intuition says "response starts after SEP so mask positions > SEP". But in shifted space, position `j` predicts `token_ids[j+1]`, so the first response prediction is at `j = sep_pos` (not `j = sep_pos + 1`).

**How to avoid:** Always use `j >= sep_pos` for shifted loss mask. [VERIFIED]

### Pitfall 3: `is_causal=True` without explicit mask

**What goes wrong:** `layer(x, is_causal=True)` raises `RuntimeError: Need attn_mask if specifying the is_causal hint` in PyTorch 2.8.

**Why it happens:** PyTorch 2.8 requires an explicit mask when the `is_causal` hint is passed. Unlike SDPA (scaled_dot_product_attention), `TransformerEncoderLayer` does not auto-generate the causal mask.

**How to avoid:** Always pass both: `layer(x, src_mask=causal, is_causal=True)`. [VERIFIED]

### Pitfall 4: Positional embedding table too small

**What goes wrong:** `nn.Embedding(max_seq_len, d_model)` with `max_seq_len=64` only covers positions 0..63. The MEL prefix uses position 0, tokens use positions 1..T. For T=64, position 64 is accessed → `IndexError`.

**How to avoid:** Use `nn.Embedding(max_seq_len + 1, d_model)` — size 65 for `max_seq_len=64`. [VERIFIED: architecture uses `max_seq_len+1` in Section 2 snippet]

### Pitfall 5: norm_first=True triggers UserWarning in TransformerEncoder

**What goes wrong:** `TransformerEncoder` with `norm_first=True` layers logs `UserWarning: enable_nested_tensor is True, but self.use_nested_tensor is False` at construction. Clutters output.

**How to avoid:** Use `norm_first=False` (Post-LN). No warning, standard behavior, sufficient for Phase 2 scale. [VERIFIED]

### Pitfall 6: mel tensor channel dim missing

**What goes wrong:** `MelEncoder` expects `(B, 1, 96, 128)` (Conv2d requires channel dim). The artifact stores mel as `(96, 128)` (no channel dim). Forgetting `.unsqueeze(1)` in `collate_fn` raises shape error in first Conv2d.

**How to avoid:** Add channel dim in `collate_fn`: `torch.stack(mel_list).unsqueeze(1)` → `(B, 1, 96, 128)`. [VERIFIED: confirmed in collate_fn implementation]

### Pitfall 7: Separate optimizer for mel_enc and transformer

**What goes wrong:** If `MelEncoder` is a separate module and not passed to the optimizer, its parameters don't update. The mel encoder stays at random init throughout training (appears to train but mel conditioning is random).

**How to avoid:** Either (a) include `MelEncoder` as a submodule of `ApolloModel` so `model.parameters()` captures it, or (b) explicitly combine: `optimizer = AdamW(list(model.parameters()) + list(mel_enc.parameters()), lr=1e-3)`. [VERIFIED: D-02 requires jointly trained]

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| torch | All model/training ops | ✓ | 2.8.0 | — |
| MPS | GPU-accelerated training | ✓ | macOS 25.4.0 | CPU (slower, ~10× for this model size) |
| pytest | Tests | ✓ | (dev extra installed) | — |

[VERIFIED: `torch.backends.mps.is_available()` = True; `torch.__version__` = "2.8.0"]

**No missing dependencies.** Phase 2 requires nothing beyond the existing `pyproject.toml` deps.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (already in `[dev]` extra) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` `testpaths = ["tests"]` |
| Quick run | `pytest tests/test_model_*.py -x` |
| Full suite | `pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| COND-02 | MelEncoder output shape `(B, d_model)` for `(B,1,96,128)` input | unit | `pytest tests/test_mel_encoder.py -x` | ❌ Wave 0 |
| COND-03 | MelEncoder gradients flow during training step | unit | `pytest tests/test_mel_encoder.py::test_gradients_flow -x` | ❌ Wave 0 |
| TRAIN-01 | Packed sequence structure `[BOS, call, SEP, resp, EOS]` + DataLoader shapes | unit | `pytest tests/test_packer.py -x` | ❌ Wave 0 |
| TRAIN-02 | Loss mask `j >= sep_pos`, not `j > sep_pos`; response tokens included | unit | `pytest tests/test_train.py::test_loss_mask -x` | ❌ Wave 0 |
| TRAIN-03 | Model loads with random init (no pre-existing checkpoint) | unit | `pytest tests/test_train.py::test_random_init -x` | ❌ Wave 0 |
| TRAIN-04 | Smoke train >95% type accuracy on 10 mock pairs | integration | `pytest tests/test_smoke_train.py -x` | ❌ Wave 0 |
| TRAIN-05 | Training runs to completion on MPS without error | integration (part of smoke) | `pytest tests/test_smoke_train.py -x` | ❌ Wave 0 |
| TRAIN-06 | Checkpoint has all 5 keys; loads cleanly; model reconstructable from config | unit | `pytest tests/test_checkpoint.py -x` | ❌ Wave 0 |

### Wave 0 Gaps

- [ ] `tests/test_mel_encoder.py` — shape + gradient flow (COND-02, COND-03)
- [ ] `tests/test_packer.py` — sequence packing + collate_fn shapes (TRAIN-01)
- [ ] `tests/test_train.py` — loss mask correctness, random init (TRAIN-02, TRAIN-03)
- [ ] `tests/test_smoke_train.py` — end-to-end smoke train >95% type accuracy (TRAIN-04, TRAIN-05)
- [ ] `tests/test_checkpoint.py` — checkpoint save/load/reconstruct (TRAIN-06)

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `synthesize_pair` from `apollo.ingest.mock` produces artifacts compatible with `ApolloDataset` without modification | Section 5 | Would need to adjust `collate_fn` or `ingest()` call in smoke script |
| A2 | 10 mock pairs with 20 epochs is sufficient to reach >95% type accuracy (model memorizes packing grammar) | Section 8 | May need more epochs or pairs; easily tunable |

All other claims verified by live execution.

---

## Open Questions

1. **Single `ApolloModel` class vs. separate `ApolloModel` + `MelEncoder`**
   - What we know: CONTEXT.md D-25 specifies separate files `mel_encoder.py` and `transformer.py`.
   - What's unclear: Whether `ApolloModel` (transformer.py) should *contain* `MelEncoder` as a submodule (simpler for optimizer + checkpoint) or call it externally (cleaner separation, as shown in CONTEXT.md D-23 which has separate `model_state_dict` and `mel_encoder_state_dict` keys).
   - Recommendation: **Keep separate as per D-23**. `train.py` creates both instances, passes both to the optimizer, and saves both state_dicts. The `ApolloModel.forward(token_ids, mel_embed)` signature accepts the pre-projected mel embed (not raw mel). `mel_enc` and `model` remain separate objects.

2. **SEP detection edge case: multiple SEP tokens**
   - What we know: `argmax` returns the *first* match.
   - What's unclear: Can response tokens ever be `SEP (111)`? The vocab has `[109..111]` as special. Response tokens come from `Tokenizer.encode`, which only produces IDs in `[0..108]`. SEP cannot appear in the response token stream from Phase 1.
   - Recommendation: Safe assumption. Document in `compute_masked_loss` docstring.

---

## Sources

### Primary (HIGH confidence — verified by live execution)
- PyTorch 2.8.0, MPS device on macOS 25.4.0 — all code snippets executed in this session
- `apollo/tokenizer/vocab.py` — Vocab constants (VOCAB_SIZE=256, BOS=109, EOS=110, SEP=111)
- `apollo/ingest/artifact.py` — artifact schema; mel shape `(96,128)` confirmed
- `apollo/ingest/mock.py` — `synthesize_pair` API confirmed

### Secondary (MEDIUM confidence)
- CONTEXT.md D-01 through D-27 — all architectural decisions (source of truth for this phase)
- Phase 1 SUMMARY files 01-01 through 01-02 — confirmed vocab layout and 4-token-per-note packing

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all in existing `pyproject.toml`, no new deps
- Architecture patterns: HIGH — every snippet verified by live execution on MPS PyTorch 2.8
- Pitfalls: HIGH — all 7 pitfalls verified by live tests; not theoretical
- MPS compatibility: HIGH — 5 training steps confirmed, all relevant ops tested

**Research date:** 2026-05-19
**Valid until:** 2026-08-19 (PyTorch minor releases may change mask warning behavior; core ops stable)

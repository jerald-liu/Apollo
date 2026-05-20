# Phase 3: Corpus & Inference — Pattern Map

**Mapped:** 2026-05-19
**Files analyzed:** 5 (2 new scripts, 2 new test files, 1 directory stub)
**Analogs found:** 5 / 5

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `apollo/scripts/train.py` | script/CLI | batch (train loop) | `apollo/scripts/train_smoke.py` | exact |
| `apollo/scripts/generate.py` | script/CLI | request-response (inference) | `apollo/scripts/ingest_corpus.py` (CLI shell) + `apollo/scripts/train_smoke.py` (model usage) | role-match |
| `tests/test_generate.py` | test | request-response | `tests/test_smoke_train.py` | role-match |
| `tests/test_train.py` (extend) | test | batch | `tests/test_smoke_train.py` + `tests/test_train.py` | exact |
| `data/pairs/` | directory stub | — | `data/raw/maestro-v3.0.0/` (concept only) | no-analog |

---

## Pattern Assignments

### `apollo/scripts/train.py` (script/CLI, batch training)

**Analog:** `apollo/scripts/train_smoke.py`

**Imports pattern** (`train_smoke.py` lines 19–38):
```python
from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import torch
from torch.utils.data import DataLoader

from apollo.ingest.artifact import ingest
from apollo.ingest.mock import synthesize_pair
from apollo.model import (
    ApolloDataset,
    ApolloModel,
    collate_fn,
    get_device,
    run_training,
)
from apollo.model.metrics import token_category
from apollo.model.train import save_checkpoint
```

For `train.py`, replace `run_training` with `train_epoch` (to plug in the scheduler), add `load_checkpoint` for any potential resume, and add `compute_masked_loss` for the held-out eval pass. The `synthesize_pair` / `tempfile` imports are dropped (train.py loads real corpus).

**train.py import block (net-new):**
```python
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

import torch
from torch.utils.data import DataLoader

from apollo.ingest import IngestError, ingest
from apollo.model import (
    ApolloDataset,
    ApolloModel,
    collate_fn,
    get_device,
    train_epoch,
)
from apollo.model.train import compute_masked_loss, save_checkpoint
```

**CLI arg parser pattern** (`ingest_corpus.py` lines 23–41):
```python
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the Apollo tokenized corpus artifact."
    )
    parser.add_argument("pairs_root", help="Path to the data/pairs/ directory")
    parser.add_argument("--output", default="artifacts/tokenized_v1.pt", ...)
    parser.add_argument("--tempo-bpm", type=float, default=120.0, ...)
    args = parser.parse_args(argv)
    try:
        ...
        return 0
    except IngestError as e:
        print(f"INGEST FAILED: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"UNEXPECTED ERROR: {e!r}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    sys.exit(main())
```

`train.py` uses the same `main(argv=None) -> int` + `sys.exit(main())` shell. Exit codes: 0=success, 1=IngestError, 2=unexpected.

**train.py CLI flags** (per RESEARCH.md §Training Script Design):
```python
parser.add_argument("pairs_root")
parser.add_argument("--epochs",     type=int,   default=300)
parser.add_argument("--lr",         type=float, default=1e-3)
parser.add_argument("--batch-size", type=int,   default=4)
parser.add_argument("--log-every",  type=int,   default=10)
parser.add_argument("--iteration",  type=int,   default=1)
parser.add_argument("--output-dir", type=str,   default="models")
parser.add_argument("--log-dir",    type=str,   default="logs")
parser.add_argument("--seed",       type=int,   default=0)
parser.add_argument("--no-csv",     action="store_true")
```

**Model config constant pattern** (`train_smoke.py` lines 41–48):
```python
DEFAULT_MODEL_CONFIG = {
    "vocab_size": 256,
    "d_model": 128,
    "n_layers": 4,
    "n_heads": 4,
    "d_ff": 512,
    "max_seq_len": 64,
}
```
Copy verbatim into `train.py`.

**Dataset + DataLoader construction pattern** (`train_smoke.py` lines 116–117):
```python
ds = ApolloDataset(artifact, split="all")
dl = DataLoader(ds, batch_size=batch_size, shuffle=True, collate_fn=collate_fn)
```
For `train.py`, use `split="train"` for the train loader and build a separate held-out loader:
```python
train_ds  = ApolloDataset(artifact, split="train")
heldout_ds = ApolloDataset(artifact, split="held_out")
train_loader   = DataLoader(train_ds,   batch_size=args.batch_size, shuffle=True,  collate_fn=collate_fn)
heldout_loader = DataLoader(heldout_ds, batch_size=args.batch_size, shuffle=False, collate_fn=collate_fn)
```

**Scheduler construction** (RESEARCH.md §Scheduler Construction, D-09):
```python
optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)
steps_per_epoch = len(train_loader)
total_steps = args.epochs * steps_per_epoch
scheduler = torch.optim.lr_scheduler.OneCycleLR(
    optimizer,
    max_lr=args.lr,
    total_steps=total_steps,
    pct_start=0.05,       # 5% warmup
    anneal_strategy="cos",
)
```

**Train loop + held-out logging** (RESEARCH.md §Held-Out Loss Logging, D-12):
```python
for epoch in range(args.epochs):
    train_loss = train_epoch(model, train_loader, optimizer, device, scheduler=scheduler)
    # NOTE: do NOT call scheduler.step() here — train_epoch already steps per batch

    if (epoch + 1) % args.log_every == 0:
        held_loss = _evaluate_heldout_loss(model, heldout_loader, device)
        print(f"epoch {epoch+1}/{args.epochs}  train_loss={train_loss:.4f}  held_loss={held_loss:.4f}")
        if csv_writer:
            csv_writer.writerow({"epoch": epoch+1, "train_loss": train_loss, "held_loss": held_loss})
```

**`_evaluate_heldout_loss` helper** (mirrors `_evaluate_type_accuracy` in `train_smoke.py` lines 61–95):
```python
@torch.no_grad()
def _evaluate_heldout_loss(model, dataloader, device) -> float:
    model.eval()
    total_loss = 0.0
    n_batches = 0
    for token_ids, pad_mask, mel in dataloader:
        token_ids = token_ids.to(device)
        pad_mask  = pad_mask.to(device)
        mel       = mel.to(device).float()
        logits    = model(token_ids, mel, key_padding_mask=pad_mask)
        loss      = compute_masked_loss(logits, token_ids)
        total_loss += loss.item()
        n_batches += 1
    model.train()
    return total_loss / max(n_batches, 1)
```

**Checkpoint naming + save** (D-10; mirrors `train_smoke.py` lines 131–148):
```python
timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
out_path  = Path(args.output_dir) / f"run-{args.iteration:02d}-{timestamp}.pt"

training_meta = {
    "n_epochs":   args.epochs,
    "n_pairs":    artifact["metadata"]["n_pairs"],
    "final_loss": float(train_loss),
    "type_accuracy": 0.0,   # Phase 3 does not compute type_accuracy
    "timestamp":  datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
}
save_checkpoint(
    model=model,
    vocab_dict=artifact["vocab"],
    model_config=DEFAULT_MODEL_CONFIG,
    training_meta=training_meta,
    out_path=str(out_path),
)
```

**Summary line** (CONTEXT.md `## Specific Ideas`):
```python
print(
    f"train done: n_pairs={n_pairs} split=train/held_out={n_train}/{n_held} "
    f"epochs={args.epochs} final_loss={train_loss:.4f} held_loss={held_loss:.4f} "
    f"checkpoint={out_path}"
)
```

---

### `apollo/scripts/generate.py` (script/CLI, request-response inference)

**Primary analog (CLI shell):** `apollo/scripts/ingest_corpus.py`
**Secondary analog (model usage):** `apollo/scripts/train_smoke.py` + `tests/test_checkpoint.py`

**Imports pattern:**
```python
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import pretty_midi
import torch

from apollo.ingest.audio import MelExtractor
from apollo.ingest.midi import load_notes
from apollo.model import ApolloModel, BOS, EOS, SEP
from apollo.model.train import load_checkpoint
from apollo.tokenizer.decoder import decode_tokens
from apollo.tokenizer.encoder import Tokenizer
from apollo.tokenizer.vocab import Vocab
```

**CLI arg parser pattern** (follows `ingest_corpus.py` shell):
```python
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a MIDI response to a call phrase."
    )
    parser.add_argument("checkpoint",  help="Path to .pt checkpoint file")
    parser.add_argument("call_mid",    help="Path to call.mid")
    parser.add_argument("call_wav",    help="Path to call.wav")
    parser.add_argument("--n",           type=int,   default=1,   help="Number of responses to generate")
    parser.add_argument("--temperature", type=float, default=0.8, help="Sampling temperature (D-14)")
    parser.add_argument("--top-k",       type=int,   default=10,  help="Top-k sampling (D-14)")
    parser.add_argument("--max-tokens",  type=int,   default=24,  help="Max response tokens (D-15)")
    args = parser.parse_args(argv)
    try:
        ...
        return 0
    except Exception as e:
        print(f"ERROR: {e!r}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
```

**Checkpoint loading + model reconstruction** (`tests/test_checkpoint.py` lines 87–100, `train_smoke.py` lines 131–148):
```python
ckpt  = load_checkpoint(args.checkpoint, map_location="cpu")
model = ApolloModel(**ckpt["model_config"])
model.load_state_dict(ckpt["model_state_dict"])
device = get_device()
model  = model.to(device)
model.eval()
vocab  = Vocab()   # canonical constants; ckpt["vocab"] used only for BOS/EOS/SEP spot-check
```

**Mel extraction** (`apollo/ingest/audio.py` lines 61–102):
```python
mx  = MelExtractor()
mel = mx(str(call_wav_path), str(call_wav_path.parent))   # returns (96, 128) float32
mel_batch = mel.unsqueeze(0).unsqueeze(0).to(device)      # (1, 1, 96, 128)
```

**BPM extraction** (RESEARCH.md §API Contracts — load_notes BPM extraction):
```python
# load_notes does NOT return BPM; call estimate_tempo directly (RESEARCH pitfall #6)
call_bpm = float(pretty_midi.PrettyMIDI(str(call_mid_path)).estimate_tempo())
```

**Call token encoding for inference prefix** (RESEARCH.md §Sampling Loop Detail):
```python
call_notes = load_notes(str(call_mid_path), str(call_mid_path.parent), tempo_bpm=call_bpm)
tokenizer  = Tokenizer(vocab, tempo_bpm=call_bpm)
call_token_ids = tokenizer.encode(call_notes)

# Build inference prefix: [BOS, call_tokens..., SEP]  (matches training layout)
prefix_ids = [BOS] + call_token_ids + [SEP]
```

**Autoregressive sampling loop** (RESEARCH.md §Sampling Loop Detail):
```python
generated = []
for _ in range(args.max_tokens):
    ids_tensor = torch.tensor([prefix_ids + generated], dtype=torch.long, device=device)
    with torch.no_grad():
        logits = model(ids_tensor, mel_batch, key_padding_mask=None)
    next_logit = logits[0, -1, :] / args.temperature        # (256,)
    top_k_vals, top_k_ids = torch.topk(next_logit, k=args.top_k)
    probs     = torch.softmax(top_k_vals, dim=-1)
    chosen    = torch.multinomial(probs, num_samples=1)
    next_id   = top_k_ids[chosen].item()
    if next_id == EOS:
        break
    generated.append(next_id)
```

**Invalid token handling + decode** (D-16; RESEARCH.md §Invalid Token Handling):
```python
# Strip any stray BOS/SEP/EOS before decode_tokens (RESEARCH pitfall #1)
response_ids = [t for t in generated if t not in (BOS, SEP, EOS)]
# Truncate to complete 4-groups; decode_tokens drops trailing partials silently
response_ids = response_ids[: (len(response_ids) // 4) * 4]
n_invalid = 0
try:
    notes = decode_tokens(response_ids, vocab, tempo_bpm=call_bpm)
except ValueError as exc:
    warnings.warn(f"decode_tokens raised {exc}; attempting truncation")
    # Walk groups until error; keep valid prefix
    notes = []
    for i in range(0, len(response_ids) - 3, 4):
        try:
            n = decode_tokens(response_ids[i:i+4], vocab, tempo_bpm=call_bpm)
            notes.extend(n)
        except ValueError:
            n_invalid += 1
if n_invalid:
    print(f"WARNING: {n_invalid} invalid token group(s) skipped", file=sys.stderr)
```

**MIDI write + non-destructive output naming** (D-17; `apollo/ingest/mock.py` lines 55–65 for pretty_midi usage):
```python
# pretty_midi write pattern (from mock.py)
pm   = pretty_midi.PrettyMIDI(initial_tempo=call_bpm)
inst = pretty_midi.Instrument(program=0)
for note in notes:
    inst.notes.append(
        pretty_midi.Note(
            velocity=note.velocity,
            pitch=note.pitch,
            start=note.start,
            end=note.end,
        )
    )
pm.instruments.append(inst)
pm.write(str(out_path))

# Non-destructive output naming (D-17): find next available response_NNN.mid index
def _next_response_path(pair_dir: Path) -> Path:
    idx = 1
    while True:
        candidate = pair_dir / f"response_{idx:03d}.mid"
        if not candidate.exists():
            return candidate
        idx += 1
```

**Summary output** (CONTEXT.md `## Specific Ideas`, Claude's discretion):
```python
print(f"Generated {len(notes)} note(s), {n_invalid} invalid token(s) skipped -> {out_path}")
```

---

### `tests/test_generate.py` (test, request-response)

**Analog:** `tests/test_smoke_train.py`

**Imports pattern** (`test_smoke_train.py` lines 14–28):
```python
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import torch

import apollo.scripts.generate as generate
from apollo.ingest.mock import synthesize_pair
from apollo.ingest.artifact import ingest
from apollo.model import ApolloModel, get_device
from apollo.model.train import save_checkpoint, load_checkpoint
```

**Mock artifact + checkpoint fixture pattern** (`test_smoke_train.py` lines 35–52 + `test_checkpoint.py` lines 57–70):
```python
MODEL_CONFIG = {
    "vocab_size": 256, "d_model": 128, "n_layers": 4,
    "n_heads": 4, "d_ff": 512, "max_seq_len": 64,
}

@pytest.fixture(scope="module")
def mock_ckpt(tmp_path_factory):
    """Synthesize one pair, build artifact, save untrained checkpoint."""
    from apollo.ingest.mock import synthesize_pair
    from apollo.ingest.artifact import ingest

    root = tmp_path_factory.mktemp("gen_pairs")
    synthesize_pair(root, nnn="000")
    artifact = ingest(str(root))

    torch.manual_seed(0)
    model = ApolloModel(**MODEL_CONFIG)
    ckpt_path = root / "test.pt"
    save_checkpoint(
        model=model,
        vocab_dict=artifact["vocab"],
        model_config=MODEL_CONFIG,
        training_meta={"n_epochs": 0, "n_pairs": 1, "final_loss": 0.0, "type_accuracy": 0.0, "timestamp": ""},
        out_path=str(ckpt_path),
    )
    return ckpt_path, root / "000"
```

**Smoke test structure** (`test_smoke_train.py` lines 35–52):
```python
def test_generate_smoke_creates_response_midi(mock_ckpt, tmp_path):
    """Smoke: generate.main() on a mock pair creates response_001.mid."""
    ckpt_path, pair_dir = mock_ckpt
    rc = generate.main([
        str(ckpt_path),
        str(pair_dir / "call.mid"),
        str(pair_dir / "call.wav"),
    ])
    assert rc == 0
    assert (pair_dir / "response_001.mid").exists()
```

**MIDI content assertion** (mirrors checkpoint round-trip test style):
```python
def test_generate_output_is_valid_midi(mock_ckpt):
    """response_001.mid is parseable pretty_midi with >= 1 note."""
    import pretty_midi
    _, pair_dir = mock_ckpt
    pm = pretty_midi.PrettyMIDI(str(pair_dir / "response_001.mid"))
    assert len(pm.instruments) >= 1
    all_notes = [n for inst in pm.instruments for n in inst.notes]
    assert len(all_notes) >= 1
```

**N-sample output test** (D-17):
```python
def test_generate_n_samples_naming(mock_ckpt):
    """--n 3 creates response_002.mid and response_003.mid (001 exists from smoke test)."""
    ckpt_path, pair_dir = mock_ckpt
    rc = generate.main([
        str(ckpt_path),
        str(pair_dir / "call.mid"),
        str(pair_dir / "call.wav"),
        "--n", "3",
    ])
    assert rc == 0
    # 001 already exists; next available indices are 002, 003, 004
    for i in [2, 3, 4]:
        assert (pair_dir / f"response_{i:03d}.mid").exists()
```

---

### `tests/test_train.py` — extensions for train.py (test, batch)

**Analog:** `tests/test_smoke_train.py` (for CLI smoke pattern) + existing `tests/test_train.py` (for fixture pattern)

The existing `tests/test_train.py` already covers `train_epoch`, `compute_masked_loss`, and metrics. New tests extend it OR live in a separate `tests/test_train_real.py`. Recommended: add a new class `TestTrainCLI` to existing `tests/test_train.py`.

**Fixture pattern** (`tests/test_train.py` lines 40–56):
```python
@pytest.fixture(scope="module")
def mock_artifact(tmp_path_factory):
    from apollo.ingest.mock import synthesize_pair
    from apollo.ingest.artifact import ingest

    root = tmp_path_factory.mktemp("pairs")
    for i in range(6):
        synthesize_pair(root, nnn=f"{i:03d}")
    synthesize_pair(root, nnn="006")   # heldout
    return ingest(root)
```

**train.py CLI smoke test** (mirrors `test_smoke_train.py` lines 123–138):
```python
def test_train_cli_smoke_creates_checkpoint(tmp_path):
    """train.main() on mock pairs creates a run-01-*.pt checkpoint."""
    import apollo.scripts.train as train_script
    from apollo.ingest.mock import synthesize_pair
    from apollo.ingest.artifact import ingest

    root = tmp_path / "pairs"
    for i in range(7):
        synthesize_pair(root, nnn=f"{i:03d}")

    rc = train_script.main([
        str(root),
        "--epochs", "5",
        "--iteration", "1",
        "--output-dir", str(tmp_path / "models"),
        "--log-dir",    str(tmp_path / "logs"),
        "--no-csv",
    ])
    assert rc == 0
    checkpoints = list((tmp_path / "models").glob("run-01-*.pt"))
    assert len(checkpoints) == 1
    assert checkpoints[0].name.startswith("run-01-")
```

**Held-out logging test:**
```python
def test_train_cli_logs_held_out(tmp_path, capsys):
    """train.main() prints held_loss every --log-every epochs."""
    import apollo.scripts.train as train_script
    from apollo.ingest.mock import synthesize_pair

    root = tmp_path / "pairs"
    for i in range(7):
        synthesize_pair(root, nnn=f"{i:03d}")

    train_script.main([
        str(root),
        "--epochs", "10",
        "--log-every", "5",
        "--output-dir", str(tmp_path / "models"),
        "--no-csv",
    ])
    captured = capsys.readouterr()
    assert "held_loss=" in captured.out
```

---

## Shared Patterns

### Device Selection
**Source:** `apollo/model/train.py` lines 30–33
**Apply to:** Both `train.py` and `generate.py`
```python
from apollo.model.train import get_device
device = get_device()   # returns torch.device("mps") or torch.device("cpu")
```

### Checkpoint Save/Load
**Source:** `apollo/model/train.py` lines 155–190
**Apply to:** `train.py` (save), `generate.py` (load)
```python
# Save (train.py)
save_checkpoint(model=model, vocab_dict=artifact["vocab"],
                model_config=DEFAULT_MODEL_CONFIG, training_meta=training_meta,
                out_path=str(out_path))

# Load (generate.py)
ckpt  = load_checkpoint(str(ckpt_path), map_location="cpu")
model = ApolloModel(**ckpt["model_config"])
model.load_state_dict(ckpt["model_state_dict"])
model.eval()
```

### Exit-code CLI Shell
**Source:** `apollo/scripts/ingest_corpus.py` lines 23–59
**Apply to:** Both `train.py` and `generate.py`
```python
def main(argv=None) -> int:
    ...
    try:
        ...
        return 0
    except IngestError as e:
        print(f"INGEST FAILED: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"UNEXPECTED ERROR: {e!r}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    sys.exit(main())
```

### Eval Mode + no_grad
**Source:** `apollo/scripts/train_smoke.py` lines 61–95 (`_evaluate_type_accuracy`)
**Apply to:** `_evaluate_heldout_loss` in `train.py`, inference loop in `generate.py`
```python
model.eval()
with torch.no_grad():
    logits = model(token_ids, mel, key_padding_mask=pad_mask)  # or key_padding_mask=None for inference
model.train()   # restore after eval pass (train.py only)
```

### pretty_midi Write
**Source:** `apollo/ingest/mock.py` lines 55–65
**Apply to:** `generate.py` (response MIDI write)
```python
pm   = pretty_midi.PrettyMIDI(initial_tempo=call_bpm)
inst = pretty_midi.Instrument(program=0)
for p, d in zip(pitches, durations):
    inst.notes.append(pretty_midi.Note(velocity=velocity, pitch=p, start=t, end=t + d))
pm.instruments.append(inst)
pm.write(str(path))
```

### Mock Artifact Fixture
**Source:** `tests/test_train.py` lines 40–56
**Apply to:** `tests/test_generate.py`, `tests/test_train.py` extensions
```python
@pytest.fixture(scope="module")
def mock_artifact(tmp_path_factory):
    from apollo.ingest.mock import synthesize_pair
    from apollo.ingest.artifact import ingest
    root = tmp_path_factory.mktemp("pairs")
    for i in range(6):
        synthesize_pair(root, nnn=f"{i:03d}")
    synthesize_pair(root, nnn="006")
    return ingest(root)
```

### DataLoader Construction
**Source:** `apollo/scripts/train_smoke.py` lines 116–117
**Apply to:** `train.py`
```python
ds = ApolloDataset(artifact, split="train")
dl = DataLoader(ds, batch_size=batch_size, shuffle=True, collate_fn=collate_fn)
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `data/pairs/` directory stub | directory / corpus | — | No comparable hand-authored data directory exists; prior `data/raw/maestro-v3.0.0/` is a completely different corpus type. Planner documents authoring conventions only. |

---

## Critical Pitfalls to Encode in Plans

These are RESEARCH-verified traps the planner must call out explicitly in plan action items:

| Pitfall | File | What Plan Must Say |
|---|---|---|
| Strip BOS/SEP/EOS before `decode_tokens` | `generate.py` | `response_ids = [t for t in generated if t not in (BOS, SEP, EOS)]` |
| `model.eval()` + `torch.no_grad()` | `generate.py` | Both required before inference loop |
| `mel.unsqueeze(0).unsqueeze(0)` | `generate.py` | MelExtractor returns `(96,128)`; model needs `(1,1,96,128)` |
| `OneCycleLR.step()` called per batch NOT per epoch | `train.py` | Do NOT call `scheduler.step()` in the outer epoch loop — `train_epoch` already steps per batch |
| BPM via `pretty_midi.PrettyMIDI(path).estimate_tempo()` | `generate.py` | `load_notes` does NOT return BPM |
| Inference prefix is `[BOS, call_tokens..., SEP]` NOT just `[BOS]` | `generate.py` | Must match training packer layout from `apollo/model/packer.py` lines 79–107 |
| `data/pairs/` does not exist | `train.py` | Wave 0 task: `mkdir -p data/pairs/`; print clear warning if n_pairs < 30 |

---

## Metadata

**Analog search scope:** `apollo/scripts/`, `tests/`, `apollo/model/`, `apollo/ingest/`, `apollo/tokenizer/`
**Files scanned:** 14 source files + 9 test files
**Pattern extraction date:** 2026-05-19

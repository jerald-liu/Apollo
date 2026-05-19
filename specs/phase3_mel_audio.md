# Phase 3 — Mel + Audio Integration

## Goal
Replace the 5-scalar hand-crafted `SpectralEncoder` with a learned
mel spectrogram encoder. The model receives raw perceptual audio context
at each token position instead of pre-digested scalars someone chose
backwards from synth CCs.

Target: val loss < 2.0, richer timbral conditioning, unlocks multi-scale
(fine/mid/coarse) in Phase 3.2.

---

## Why mel first

Current `SpectralEncoder`: 2-layer MLP on 5 floats (brightness, attack,
richness, warmth, flux). These are means/peaks over STFT frames — one number
per timbral dimension per note. The model gets a collapsed summary, not the
actual spectral texture.

A mel spectrogram patch gives the model:
- Attack transient shape (not just peak onset)
- Harmonic structure (partial ratios, inharmonicity)
- Noise floor / breathiness
- Temporal envelope within the note body

All of this is present in mel but collapsed away in the 5 scalars.

---

## Architecture

### Current
```
tokens → token_emb + pos_emb + spectral_emb(5 scalars) → Transformer → logits
```

### Phase 3.1 (this plan)
```
tokens → token_emb + pos_emb + mel_emb(mel patch) → Transformer → logits
```

### Phase 3.2 (future — multi-scale)
```
tokens → token_emb + pos_emb
       + mel_fine_emb   (~23ms hop,  transients)
       + mel_mid_emb    (~200ms hop, note body)
       + mel_coarse_emb (~2s hop,    phrase arc)
       → Transformer → logits
```

---

## Implementation — 4 tasks

### Task 1: Mel preprocessing (`scripts/preprocess.py`)

Add `--mel` flag (separate from `--spectral`). When set:

1. For each MIDI file, find the paired audio (`.wav` or `.flac`, same stem).
2. Load audio at `sr=22050`.
3. Compute log-mel: `n_mels=128`, `n_fft=2048`, `hop_length=512` (23ms frames).
   → `log_mel = librosa.power_to_db(librosa.feature.melspectrogram(...))`
4. For each token window in the file, determine the time span
   `[t_start, t_end]` seconds from the event timestamps stored during
   tokenization. Extract the mel slice: `mel[frame_start:frame_end, :]`.
5. Pad/crop each slice to a fixed `mel_frames` length (e.g. 256 frames ≈ 5.9s
   at hop=512 — covers a 512-token window of ~100 events at typical piano tempo).
6. Save `{split}_mel.npy` of shape `(n_windows, mel_frames, n_mels)` as
   `float16` (halves storage: 35K × 256 × 128 × 2B ≈ 2.3GB per split).
7. Add `mel_frames`, `n_mels` to `meta.json`.

**Time alignment note**: the current token windows don't store absolute onset
times. Need to record `window_onset_time` during tokenization and save as
`{split}_window_times.npy` (shape `(n_windows,)` float32). This is a small
addition to `preprocess.py`.

### Task 2: `MelEncoder` (`src/model.py`)

```python
class MelEncoder(nn.Module):
    """
    Encodes a mel spectrogram patch into a single d_model vector
    that is broadcast to all token positions in the window.

    Input:  (B, T_frames, n_mels)  — e.g. (B, 256, 128)
    Output: (B, 1, d_model)        — broadcast over tokens
    """
    def __init__(self, n_mels=128, d_model=384):
        super().__init__()
        self.conv = nn.Sequential(
            # (B, 1, T, n_mels) — treat as single-channel image
            nn.Conv2d(1, 32, kernel_size=(3, 3), padding=1),
            nn.GELU(),
            nn.Conv2d(32, 64, kernel_size=(3, 3), padding=1),
            nn.GELU(),
            nn.AdaptiveAvgPool2d((8, 8)),   # → (B, 64, 8, 8)
        )
        self.proj = nn.Linear(64 * 8 * 8, d_model)
        self.norm = nn.LayerNorm(d_model)

    def forward(self, mel):
        # mel: (B, T_frames, n_mels)
        x = mel.unsqueeze(1)              # (B, 1, T_frames, n_mels)
        x = self.conv(x)                  # (B, 64, 8, 8)
        x = x.flatten(1)                  # (B, 64*8*8)
        x = self.norm(self.proj(x))       # (B, d_model)
        return x.unsqueeze(1)             # (B, 1, d_model)  — broadcast
```

Wire into `ApolloModel.__init__`:
```python
self.mel_encoder = MelEncoder(n_mels, d_model) if n_mels > 0 else None
```

Wire into `ApolloModel.forward`:
```python
if mel_patch is not None and self.mel_encoder is not None:
    mel_emb = self.mel_encoder(mel_patch)   # (B, 1, d_model)
    h = h + mel_emb                          # broadcast over T
```

Keep old `SpectralEncoder` as a parallel optional pathway (additive) —
lets us keep the continuous spectral features if we have them, but they
are no longer the primary audio signal.

### Task 3: Dataset + training loop (`scripts/train.py`)

`PreprocessedDataset`:
- Load `{split}_mel.npy` when `mel: true` in config.
- Return `(x, y, cont, mel_patch)` from `__getitem__`.

`collate_fn`: handle the new `mel_patch` tensor.

`train()` loop:
- Pass `mel_patch` to `model.forward(x, mel_patch=mel_patch, ...)`.
- No new loss term needed — token loss already backprops through `MelEncoder`.

Add config fields:
```python
mel: bool = False
n_mels: int = 128
mel_frames: int = 256
```

### Task 4: Modal infra + config (`modal_train.py`, `configs/v3_mel.yaml`)

`modal_train.py`:
- Add `--mel` flag to `preprocess()` remote function (alongside existing
  `--spectral`).
- `preprocess --mel` downloads full MAESTRO (~101GB audio) — warn in CLI.
- Mel arrays stored on `apollo-data` volume alongside token arrays.

`configs/v3_mel.yaml`:
```yaml
mel: true
n_mels: 128
mel_frames: 256
spectral: false   # keep disabled — mel replaces scalars
dropout: 0.15
weight_decay: 0.1
label_smoothing: 0.1
pitch_aug_max: 6
velocity_aug_range: 2
max_steps: 80000
batch_size: 32    # halved — mel arrays double memory per sample
```

---

## Data requirements

| Item | Size | Notes |
|------|------|-------|
| MAESTRO full audio | ~101GB | Already on Modal volume if `--spectral` was run; otherwise re-download |
| `train_mel.npy` (fp16) | ~2.3GB | 35K × 256 × 128 × 2B |
| `val_mel.npy` (fp16) | ~0.3GB | |
| `train_window_times.npy` | ~140KB | 35K × float32 |

Check if full audio is on the volume:
```bash
modal volume ls apollo-data
```
If only MIDI was downloaded, re-run:
```bash
make modal-preprocess SPECTRAL=true   # ~101GB download, ~6h
```

---

## Sequence

```
1. Check Modal volume for full audio
   ├── present → skip to step 2
   └── absent  → make modal-preprocess SPECTRAL=true  (~6h)

2. Implement Task 1 (preprocess.py --mel)
   └── Test locally on 10 files: python scripts/preprocess.py --midi-dir ... --mel --max-files 10

3. Run mel preprocessing on Modal volume
   └── modal run modal_train.py --action preprocess --mel  (~2-3h, CPU-only)

4. Implement Tasks 2 + 3 (MelEncoder, train.py wiring)
   └── Smoke test: configs/smoke.yaml with mel=true, 5 files, 200 steps

5. Train v3: make modal-train CONFIG=configs/v3_mel.yaml
   └── Expected: val loss < 2.0 by step 40K
```

---

## Risk / fallbacks

| Risk | Mitigation |
|------|-----------|
| Full audio not on Modal volume | Re-run preprocess with SPECTRAL=true; costs ~$1 in Modal CPU time |
| Memory OOM on A100 (mel arrays large) | Reduce batch_size to 24 or use fp16 mel in dataset |
| Val loss doesn't improve over v2 | MelEncoder likely underpowered — scale up CNN, add time-distributed projection |
| Mel alignment is off (wrong window times) | Validate with `scripts/check_mel_alignment.py` (to write) that plots mel vs MIDI onset for 5 files |

---

## Future: Phase 3.2 multi-scale

Once single-scale mel is working and val < 2.0:

- Add `MelEncoderMultiScale` with fine/mid/coarse branches
- Fine: current 23ms hop
- Mid: 8× decimated mel (185ms effective hop)
- Coarse: 64× decimated mel (1.48s effective hop)
- Fuse with learned attention or simple concat + linear

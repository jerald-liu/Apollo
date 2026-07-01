---
spike: 002
name: fm-mel-conditioning
validates: "Given FM-rendered audio, when we run Apollo's real MelExtractor (COND-01 contract), then the mel is the right shape, deterministic, and varies meaningfully with FM params — carrying a timbre-conditioning signal"
verdict: VALIDATED
related: [001]
tags: [mel, cond, conditioning, torchaudio, timbre]
---

# Spike 002: FM Mel Conditioning

## What This Validates

**Given** the FM audio rendered in spike 001,
**when** we run Apollo's **real** `apollo.ingest.audio.MelExtractor` (the exact COND-01
contract: 22050 Hz, n_fft=2048, hop=512, n_mels=128, log-compressed, fixed `(96, 128)`),
**then** the mel tensor is (a) the shape the model already consumes, (b) deterministic, and
(c) meaningfully different between FM presets — i.e. it carries a usable **timbre** signal,
and (d) is more self-similar within a preset than across presets (the property the mel
encoder must exploit).

## How to Run

From the repo root, using the **project** venv (has torch/torchaudio, resolves `apollo`):

```bash
# Prereq: spike 001's render_fm.py has produced callA/callB/_det_check.wav
.venv/bin/python .planning/spikes/002-fm-mel-conditioning/mel_check.py
```

## What to Expect

```
shape A: (96, 128) ...
determinism (A vs re-render): identical=True
L2(A,B)=<large>  cos(A,B)=<below 1>  cos(A,A')=1.0000
within-preset more similar than across: True
VERDICT: PASS
```

## Results

**VERDICT: VALIDATED ✓**

```
shape A: (96, 128) dtype=torch.float32
determinism (A vs re-render): identical=True
L2(A,B)=783.38  cos(A,B)=0.8497  cos(A,A')=1.0000
within-preset more similar than across: True
mean log-mel  A=-10.934  B=-8.008
VERDICT: PASS
```

Evidence:
- **Exact contract, zero changes.** The FM-rendered WAV flows through the *production*
  `MelExtractor` untouched and yields the `(96, 128)` float32 tensor Phase 2's mel encoder
  already consumes (COND-01 / D-14). No pipeline changes needed to swap the audio source.
- **Deterministic mel.** Bit-identical re-render → bit-identical mel (`cos=1.0`,
  `torch.equal=True`). Reproducible conditioning across training runs.
- **Carries timbre.** Two FM presets give `cos(A,B)=0.85` (clearly distinguishable) and an
  L2 of 783; the brighter preset (ratio 3 / index 8) reads ~3 units higher in mean log-mel
  energy — exactly the spectral contrast a timbre encoder needs.
- **Discriminable structure.** Within-preset similarity (1.00) > across-preset (0.85),
  so the encoder has a learnable signal separating timbres.

### Signal for the build
- The renderer→mel path is a **drop-in source swap** — `call.wav` can come from DawDreamer
  instead of an Ableton bounce with no downstream change.
- The remaining open question is **not** technical feasibility but **fidelity/scope**:
  whether to (a) reimplement Operator's 4-op/11-algorithm topology in Faust for sound
  identity, or (b) adopt this controllable FM family as the v1 timbre space (which
  REQUIREMENTS.md already contemplates: "v1 timbre space constrained to one FM family so
  mel-conditioning is learnable on a small corpus"). That's a product decision, not a spike.
- Train/serve consistency: whatever renders training `call.wav` must also render
  inference-time calls — same Faust patch, same params — or the mel distribution shifts.

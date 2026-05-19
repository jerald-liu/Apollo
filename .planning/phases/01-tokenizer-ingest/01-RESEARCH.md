# Phase 1: Tokenizer & Ingest - Research

**Researched:** 2026-05-19
**Domain:** Symbolic MIDI tokenization + mel-spectrogram extraction (PyTorch / Apple Silicon MPS)
**Confidence:** HIGH

## Summary

Phase 1 is bounded plumbing: read `data/pairs/NNN/{call.mid, call.wav, response.mid}`, produce token arrays + a `(96, 128)` mel tensor per pair, and pre-tokenize the whole corpus into a single `.pt` artifact. No model, no training, no inference. The stack is conventional and well-supported: `pretty_midi` for MIDI parsing, `torchaudio` for resample + MelSpectrogram, native `torch` for tensor I/O. Existing venv already has all needed packages (`pretty_midi 0.2.11`, `torchaudio 2.8.0`, `torch 2.8.0`, `librosa 0.11.0`, `mido 1.3.3`).

The architecturally load-bearing pieces are (a) the vocab ID table — must be frozen at exact integers in code before any tokens are generated, and (b) the pre-tokenized artifact schema — that schema is the contract with Phase 2 and changes invalidate every downstream checkpoint. Everything else (libraries, file layout, helper utilities) is mechanical.

**Primary recommendation:** Use `pretty_midi` for MIDI, `torchaudio.transforms.{Resample, MelSpectrogram}` for audio, a hand-written `Vocab` dataclass + `Tokenizer` class pair, and a single flat `.pt` dict-of-tensors artifact with explicit version/schema keys.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Tokenizer — pitch vocab**
- D-01: Pitch vocab covers a 3-octave window — 37 pitches (12 × 3 + 1).
- D-02: Default window is C2–C5 (MIDI 36–72) for v1. Window may shift later; not a blocker.
- D-03: High overtones are NOT modeled as high MIDI pitches. FM/timbre carries that via mel. Do not widen pitch range without revisiting.
- D-04: MIDI notes outside the 37-pitch window during ingest → abort with offending pair path. No silent clipping/wraparound.

**Tokenizer — time/velocity/duration**
- D-05: Time-shift = 32 quantized-grid bins (one bin per 32nd note over ~2 beats). Strictly quantized.
- D-06: Velocity = 16 linear bins (4-bit).
- D-07: Duration = explicit duration token per note. Per-note packing `[time_shift, pitch, velocity, duration]` = 4 tokens/note.
- D-08: BOS/SEP/EOS wrapping happens at training packer (Phase 2), not in tokenizer. Tokenizer still defines the IDs.

**Tokenizer — vocab layout & extensibility**
- D-09: Contiguous reserved-tail-slots for future expression tokens (pitch_bend, mod_wheel, CC).
- D-10: Order: `[time_shift(32) | pitch(37) | velocity(16) | duration(TBD) | BOS/EOS/SEP | reserved]`. Reserve through ~256 for v2.

**Mel features**
- D-11: 22050 Hz sample rate for `call.wav` ingest. Downsample from 44.1/48 kHz.
- D-12: n_mels=128, n_fft=2048, hop_length=512.
- D-13: Fixed-shape mel tensor (96 frames × 128 mels). 96 frames at ~43 fps ≈ 2.23 s.
- D-14: Mel feature shape is part of the tokenizer/ingest contract. Phase 2 mel encoder accepts exactly `(B, 96, 128)`.

**Pair ingest**
- D-15: Ingest scans `data/pairs/NNN/` subdirs, parses each, returns deterministic structured dataset.
- D-16: Missing/malformed call.wav (or call.mid / response.mid) → abort with offending pair path. No silent skipping.
- D-17: NNN gaps allowed (e.g. 1, 2, 4 with no 3). Held-out split computed over the set of NNNs that actually exist.

**Storage & split**
- D-18: Pre-tokenize all pairs once into a single `.pt` artifact (tokens, mel tensors, metadata).
- D-19: Training DataLoader reads from the pre-tokenized artifact, not from disk per step.
- D-20: Hash-based split: `int(hashlib.sha1(NNN_string).hexdigest(), 16) % 5 == 0` → held out.

### Claude's Discretion
- D-21: Exact duration bin count + bin edges (16–32 range hinted in D-10).
- D-22: Concrete file paths and Python module structure.
- D-23: Any mel normalisation beyond log. Default: log-mel without further normalisation; revisit in Phase 2 if instability.

### Deferred Ideas (OUT OF SCOPE)
- Exact 3-octave window — C2–C5 placeholder, revisit after authoring.
- Pitch-shift augmentation — Phase 2 concern.
- Pitch bend / mod wheel / CC encoding — slots reserved only.
- Groove / free / off-grid timing tokens — slots reserved only.
- Variable-length mel input — fixed-shape locked for v1.
- Mel normalisation strategy beyond log-mel — Phase 2 if needed.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TOK-01 | Monophonic event tokenizer encoding pitch + velocity + timing + duration | Vocab ID Layout, Tokenizer Design sections |
| TOK-02 | Time and duration use quantized-grid bins | Vocab ID Layout (32 time bins), Duration Bin Scheme |
| TOK-03 | Vocab includes BOS, EOS, SEP special tokens | Vocab ID Layout — fixed IDs assigned |
| TOK-04 | Vocab reserves contiguous range for future bend/CC tokens | Vocab ID Layout — reserved tail through ID 255 |
| TOK-05 | Round-trip test: tokenize → decode → semantic equivalence within quantization tolerance | Round-Trip Test section |
| DATA-01 | User can author pairs in Ableton (authoring step — no code) | N/A — corpus-side requirement, satisfied externally |
| DATA-02 | Pair folder layout `data/pairs/NNN/{call.mid, call.wav, response.mid}` | Module Layout, Error Handling — strict folder validation |
| DATA-03 | Ingest pipeline reads `data/pairs/*/` and tokenizes into tensors | Module Layout, Pre-tokenized Artifact Schema |
| DATA-04 | 20% held-out split, deterministic across runs | Deterministic Split section |
| COND-01 | Mel extractor produces fixed-shape mel tensor at documented SR/hop/n_mels | Mel Pipeline section |
| COND-04 | Missing/malformed `call.wav` → report offending pair + abort | Error Handling section |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Local-only training on Apple Silicon (MPS). No Modal/cloud. *(Phase 1 has no training step but: any tensors should be CPU-resident at save time — Phase 2 moves them to MPS.)*
- Train from scratch. No MAESTRO/warm-start. *(No bearing on Phase 1 except: do not import or reference `deprecated` branch code.)*
- Monophonic both sides. *(Tokenizer assumes monophonic; if multiple notes overlap in a `.mid` file, that's a corpus-authoring bug — abort per D-04/D-16 policy.)*
- FM via mel conditioning. *(Phase 1 produces the mel input that Phase 2 consumes — `(96, 128)` is the contract.)*
- Vocab extensible by design. *(Reserved tail through ID 255.)*
- The `deprecated` branch is reference-only. Do NOT copy `src/representation.py`, `src/spectral.py`, etc.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| MIDI parsing (`call.mid`, `response.mid`) | Tokenizer module | — | Pure symbolic — owns note→token mapping |
| Audio load + resample + mel | Ingest module (audio helper) | torchaudio | Audio I/O is separate from MIDI logic; both feed into the pair record |
| Pair folder discovery + validation | Ingest module (pair scanner) | — | Filesystem + naming convention enforcement |
| Vocab definition (IDs, ranges) | Tokenizer module (`vocab.py`) | — | Single source of truth for IDs; Phase 2 imports this directly |
| Held-out split assignment | Ingest module (pure function) | — | Deterministic hash — no state, no I/O |
| Pre-tokenized artifact write/load | Ingest module (`artifact.py`) | torch.save / torch.load | Schema versioning + format contract with Phase 2 |
| Round-trip / smoke tests | `tests/` package | pytest | Independent verification of tokenizer correctness |
| Mock pair generation (for tests) | `tests/fixtures/` or `apollo/ingest/mock.py` | pretty_midi + numpy | Test-only helper; not part of production pipeline |

## Library Recommendations

### MIDI parsing: **`pretty_midi`** [VERIFIED: installed in venv at 0.2.11]

| Library | Recommend? | Rationale |
|---------|-----------|-----------|
| **pretty_midi** | **YES** | Notes already come out as objects with `pitch`, `velocity`, `start`, `end` (seconds) — duration is `end - start`, no manual pairing of NoteOn/NoteOff. Standard in MIR/MIDI research. Already installed. |
| `mido` | No | Lower-level — gives raw MIDI messages, you do NoteOn/NoteOff pairing yourself. Pointless extra work. |
| `miditoolkit` | No | Tick-based abstraction better for symbolic/composition tasks but offers nothing pretty_midi doesn't for our monophonic note-event extraction. Not installed. |

**One-liner:** `notes = pretty_midi.PrettyMIDI(path).instruments[0].notes` returns `[Note(pitch, velocity, start, end), ...]` sorted by `start`. That's the whole API surface we need. [CITED: https://craffel.github.io/pretty-midi/]

**Monophonic enforcement:** After loading, assert `for i in range(len(notes)-1): notes[i].end <= notes[i+1].start + EPS` else raise `IngestError(pair_path, "overlapping notes — corpus is monophonic")`. EPS ≈ 1e-3 s to absorb floating-point slop.

### Mel extraction: **`torchaudio`** [VERIFIED: installed in venv at 2.8.0]

| Library | Recommend? | Rationale |
|---------|-----------|-----------|
| **torchaudio** | **YES** | Native torch tensors throughout — no numpy round-trip. `Resample` and `MelSpectrogram` both compose as `nn.Module`s. MPS-friendly (CPU-side for ingest is fine; the resulting tensor saves cleanly). [CITED: https://docs.pytorch.org/audio/main/generated/torchaudio.transforms.MelSpectrogram.html] |
| `librosa` | No | Excellent library, but: returns numpy, slower than torchaudio for batch ops, mixing librosa here and torchaudio in Phase 2's encoder is a pointless API straddle. |

**One-liner:**
```python
wav, sr = torchaudio.load(path)              # (channels, samples)
wav = wav.mean(dim=0, keepdim=True)          # mono mix
wav = torchaudio.transforms.Resample(sr, 22050)(wav)
mel = torchaudio.transforms.MelSpectrogram(
    sample_rate=22050, n_fft=2048, hop_length=512, n_mels=128
)(wav)                                        # (1, 128, T)
log_mel = torch.log(mel + 1e-8).squeeze(0).transpose(0, 1)  # (T, 128)
```

## Module Layout

```
apollo/
├── pyproject.toml              # PEP 621 project metadata, deps via [project.dependencies]
├── apollo/
│   ├── __init__.py
│   ├── tokenizer/
│   │   ├── __init__.py
│   │   ├── vocab.py            # Vocab dataclass + ID table constants
│   │   ├── encoder.py          # Tokenizer.encode(notes) -> List[int]
│   │   ├── decoder.py          # Tokenizer.decode(ids) -> List[Note]
│   │   └── bins.py             # time/velocity/duration bin edges + quantization fns
│   ├── ingest/
│   │   ├── __init__.py
│   │   ├── pairs.py            # discover_pairs(root) -> List[PairPath]
│   │   ├── audio.py            # load_mel(wav_path) -> Tensor(96, 128)
│   │   ├── midi.py             # load_notes(mid_path) -> List[Note]
│   │   ├── split.py            # is_heldout(nnn: str) -> bool
│   │   ├── errors.py           # IngestError class
│   │   ├── artifact.py         # save_artifact / load_artifact (.pt format)
│   │   └── mock.py             # synthesize_pair(dir, ...) — test helper
│   └── scripts/
│       └── ingest_corpus.py    # CLI: python -m apollo.scripts.ingest_corpus data/pairs/ artifacts/v1.pt
└── tests/
    ├── __init__.py
    ├── test_tokenizer_roundtrip.py     # TOK-05
    ├── test_vocab_layout.py            # TOK-03, TOK-04 — assert ID table
    ├── test_split_determinism.py       # DATA-04
    ├── test_error_handling.py          # COND-04 + D-04 + D-16
    ├── test_ingest_smoke.py            # DATA-03 end-to-end on mock pairs
    └── fixtures/
        └── (generated pair folders for smoke test — written by mock.py at test time)
```

**Why `pyproject.toml`** [ASSUMED — confirm with user]: Modern Python standard (PEP 517/621). Sets `apollo` as an installable package so `python -m apollo.scripts.ingest_corpus ...` and `from apollo.tokenizer import Tokenizer` work uniformly in tests and scripts. Build backend: `setuptools` (simplest, no toolchain churn). If user prefers `requirements.txt` + `setup.py` or `uv` / `poetry`, fine — orthogonal to Phase 1 logic.

**Why separate `tokenizer/` and `ingest/` packages:** the tokenizer is pure symbolic — depends only on `pretty_midi` and `numpy`. The ingest layer also pulls in `torchaudio` for audio. Phase 2 model code will `from apollo.tokenizer import ...` heavily but should never need `apollo.ingest`. Clean separation = simpler import graph.

## Vocab ID Layout

**Final concrete IDs** (duration bin count = 24, see Duration Bin Scheme below):

| Range | Token Family | Count | Notes |
|-------|--------------|-------|-------|
| `0..31` | `TIME_SHIFT_<i>` | 32 | bin 0 = "no time shift / chord onset" (unused in monophonic v1 but reserved); bin 31 = ~2 beats forward |
| `32..68` | `PITCH_<midi>` | 37 | `PITCH_36` (C2) = ID 32, `PITCH_72` (C5) = ID 68 |
| `69..84` | `VELOCITY_<i>` | 16 | bin 0 = quietest, bin 15 = loudest |
| `85..108` | `DURATION_<i>` | 24 | log-spaced 30 ms → 1.5 s (see Duration Bin Scheme) |
| `109` | `BOS` | 1 | Start of sequence |
| `110` | `EOS` | 1 | End of sequence |
| `111` | `SEP` | 1 | Boundary between call and response |
| `112..255` | reserved (unused in v1) | 144 | Future: pitch_bend (~32 IDs), mod_wheel (~16 IDs), CC family (~64+ IDs), groove offsets, etc. |

**Total active v1 vocab:** 112 IDs (`0..111`). **Total allocated:** 256 (`0..255`). Model's embedding table sizes to 256 from day 1 so adding v2 tokens never requires re-init of the embedding row layout.

**Why these specific cutoffs:**
- 24 duration bins (not 16, not 32) is a deliberate compromise — see Duration Bin Scheme.
- Special tokens come *after* note tokens, not before. This makes raw-note streams produced by the tokenizer all `< 109`, so a quick sanity check (`max(token_ids) < 109` for tokenizer output) catches accidental special-token leakage.
- 144 reserved slots is generous. Worst-case projected v2 expansion: ~16 pitch-bend bins, ~16 mod-wheel bins, 32 commonly-used CCs × 8 value bins each = 256 — but realistically v2 will use coarser CC quantization and stay under 144.

**Encoded as constants in `apollo/tokenizer/vocab.py`:**
```python
@dataclass(frozen=True)
class Vocab:
    PITCH_MIN: int = 36          # C2
    PITCH_MAX: int = 72          # C5
    N_PITCH: int = 37
    N_TIME: int = 32
    N_VELOCITY: int = 16
    N_DURATION: int = 24

    TIME_OFFSET: int = 0
    PITCH_OFFSET: int = 32
    VELOCITY_OFFSET: int = 69
    DURATION_OFFSET: int = 85

    BOS: int = 109
    EOS: int = 110
    SEP: int = 111

    VOCAB_SIZE: int = 256        # includes reserved tail
    ACTIVE_VOCAB: int = 112      # IDs 0..111 actively used in v1
```

## Duration Bin Scheme

**Choice: 24 log-spaced bins from 30 ms to 1.5 s.**

**Formula** (np.logspace in base-10):
```python
import numpy as np
DURATION_EDGES = np.logspace(np.log10(0.030), np.log10(1.500), num=25)  # 25 edges → 24 bins
# edges[0]=0.030, edges[24]=1.500
# bin i covers [edges[i], edges[i+1])
def quantize_duration(d_sec: float) -> int:
    # clamp into range; out-of-range durations are valid (they get clipped to nearest edge)
    # unlike pitch, where out-of-range = error.
    d = max(0.030, min(1.500, d_sec))
    return int(np.searchsorted(DURATION_EDGES, d, side='right')) - 1   # → 0..23
def decode_duration(bin_i: int) -> float:
    # decode to bin center (geometric mean of edges)
    lo, hi = DURATION_EDGES[bin_i], DURATION_EDGES[bin_i+1]
    return float(np.sqrt(lo * hi))
```

**Bin edges (rounded to 3 decimals, seconds):**
```
0.030  0.036  0.043  0.051  0.061  0.073  0.087  0.104  0.124  0.148
0.177  0.211  0.251  0.300  0.358  0.427  0.510  0.608  0.726  0.866
1.033  1.232  1.470  1.500    ← (last edge clamped to ceiling; final bin slightly narrower)
```
*(24 bins, each ~19% wider than the previous on log scale; the last bin compresses to enforce the 1.5 s ceiling.)*

**Why 24, not 16 or 32:**
- **16 bins:** Ratio between adjacent bins is ~1.28 — too coarse. 100 ms vs 130 ms maps to the same bin; that's audible on percussive material.
- **32 bins:** Ratio is ~1.13 — finer resolution than the corpus' temporal precision (hand-authored in Ableton, grid-locked to 32nds at ~120 bpm has ~16 ms quantum, so bin widths below ~30 ms are below the floor anyway). Spends vocab slots on resolution we can't author.
- **24 bins:** Ratio ~1.19 — about 19% per bin step, which is roughly Weber-fraction-perceptible for note duration. Slightly more bins for short durations (where perceptual sensitivity is higher) is naturally provided by log spacing.

**Why log not linear:** Perception of duration is roughly log-scale (Weber's law). A 30 ms→60 ms doubling feels like the same step as 500 ms→1000 ms. Linear spacing would either waste bins at the long end or under-resolve the short end.

**Out-of-range policy (different from pitch):** Notes longer than 1.5 s or shorter than 30 ms get **clamped**, not error'd. Rationale: pitch is structurally bounded by the design (D-03, D-04 — model lives in 3 octaves). Duration just has authoring outliers (held notes, fast staccato) that shouldn't abort the pipeline. Clamping is documented behavior, not silent corruption.

## Tokenizer Design

### Class signatures

```python
# apollo/tokenizer/encoder.py
from dataclasses import dataclass
from typing import List

@dataclass
class Note:
    pitch: int          # MIDI pitch
    velocity: int       # 1..127
    start: float        # seconds
    end: float          # seconds

class Tokenizer:
    def __init__(self, vocab: Vocab, tempo_bpm: float = 120.0):
        self.vocab = vocab
        self.tempo_bpm = tempo_bpm
        # time bin width = 32nd note duration; 32 bins → 2 beats span
        beat_sec = 60.0 / tempo_bpm
        self.time_bin_sec = beat_sec / 8.0             # 32nd note
        self.time_max_sec = self.time_bin_sec * vocab.N_TIME

    def encode(self, notes: List[Note]) -> List[int]:
        """notes → flat list of token IDs, 4 per note: [time_shift, pitch, velocity, duration]"""

    def decode(self, ids: List[int]) -> List[Note]:
        """token IDs → notes. Inverse of encode (up to quantization)."""

    # Helpers (private):
    def _quantize_time_shift(self, dt_sec: float) -> int: ...
    def _quantize_velocity(self, vel: int) -> int: ...
    def _quantize_duration(self, dur_sec: float) -> int: ...
    def _pitch_to_id(self, midi_pitch: int) -> int: ...
    def _id_to_pitch(self, token_id: int) -> int: ...
```

### Encoder algorithm (high-level)

```
prev_onset = 0.0
tokens = []
for note in notes:
    dt = note.start - prev_onset
    if dt < 0 or dt > self.time_max_sec:
        raise IngestError(pair_path, f"time_shift {dt:.3f}s out of bin range")
    if not (PITCH_MIN <= note.pitch <= PITCH_MAX):
        raise IngestError(pair_path, f"pitch {note.pitch} outside {PITCH_MIN}-{PITCH_MAX}")
    tokens.append(TIME_OFFSET + quantize_time(dt))
    tokens.append(PITCH_OFFSET + (note.pitch - PITCH_MIN))
    tokens.append(VELOCITY_OFFSET + quantize_velocity(note.velocity))
    tokens.append(DURATION_OFFSET + quantize_duration(note.end - note.start))
    prev_onset = note.start
return tokens
```

### Decoder algorithm

```
notes = []
cursor = 0.0
i = 0
while i + 3 < len(ids):
    t_bin = ids[i]   - TIME_OFFSET
    p_bin = ids[i+1] - PITCH_OFFSET
    v_bin = ids[i+2] - VELOCITY_OFFSET
    d_bin = ids[i+3] - DURATION_OFFSET
    dt = decode_time(t_bin)
    cursor += dt
    notes.append(Note(
        pitch=PITCH_MIN + p_bin,
        velocity=decode_velocity(v_bin),
        start=cursor,
        end=cursor + decode_duration(d_bin),
    ))
    i += 4
return notes
```

The encoder/decoder lives in **two separate files** (`encoder.py`, `decoder.py`) but is reachable through a unified `Tokenizer` class. Rationale: round-trip tests need both, but Phase 2's training loop only imports the encoder side. Putting them in one class with both methods is fine; just keep the bin helpers in `bins.py` so they're shared and tested once.

## Mel Pipeline

### Full transform pipeline

```python
# apollo/ingest/audio.py
import torch
import torchaudio
from torchaudio.transforms import Resample, MelSpectrogram

class MelExtractor:
    TARGET_SR = 22050
    N_FFT = 2048
    HOP_LENGTH = 512
    N_MELS = 128
    TARGET_FRAMES = 96
    LOG_FLOOR = 1e-8

    def __init__(self):
        # Cached MelSpectrogram (one instance, reused across pairs)
        self.mel = MelSpectrogram(
            sample_rate=self.TARGET_SR,
            n_fft=self.N_FFT,
            hop_length=self.HOP_LENGTH,
            n_mels=self.N_MELS,
            power=2.0,         # power spectrogram (squared magnitude) — standard
            center=True,
            mel_scale='htk',   # torchaudio default — keep consistent
        )
        self._resamplers = {}  # cache Resample modules by orig SR

    def __call__(self, wav_path: str, pair_path: str) -> torch.Tensor:
        try:
            wav, sr = torchaudio.load(wav_path)        # (channels, samples), float32
        except Exception as e:
            raise IngestError(pair_path, f"failed to load {wav_path}: {e}")

        # Mono mix
        if wav.shape[0] > 1:
            wav = wav.mean(dim=0, keepdim=True)

        # Resample to 22050
        if sr != self.TARGET_SR:
            if sr not in self._resamplers:
                self._resamplers[sr] = Resample(orig_freq=sr, new_freq=self.TARGET_SR)
            wav = self._resamplers[sr](wav)

        # Mel: (1, n_mels, T) → log → (T, n_mels)
        mel = self.mel(wav)                             # (1, 128, T)
        log_mel = torch.log(mel + self.LOG_FLOOR)
        log_mel = log_mel.squeeze(0).transpose(0, 1)    # (T, 128)

        # Pad / truncate to TARGET_FRAMES
        return self._fix_frames(log_mel)

    def _fix_frames(self, log_mel: torch.Tensor) -> torch.Tensor:
        T, M = log_mel.shape
        assert M == self.N_MELS, f"expected {self.N_MELS} mels, got {M}"
        if T >= self.TARGET_FRAMES:
            return log_mel[:self.TARGET_FRAMES, :].contiguous()        # truncate
        # right-pad with log floor (silence in log-mel space)
        pad_value = float(np.log(self.LOG_FLOOR))                       # ≈ -18.42
        pad = torch.full((self.TARGET_FRAMES - T, M), pad_value, dtype=log_mel.dtype)
        return torch.cat([log_mel, pad], dim=0).contiguous()           # (96, 128)
```

**Output shape:** `(96, 128)` — frames-first. Phase 2 may permute to (128, 96) for a 2D CNN — that's its choice; the contract is (frames, n_mels).

**Padding value choice — `log(1e-8) ≈ -18.42`:**

| Option | Verdict |
|--------|---------|
| **`log(1e-8)` (log of the log_floor)** | **CHOSEN.** Consistent with how genuine silence appears in the signal — quiet frames in real audio have power near `1e-8` after log floor, so padding looks indistinguishable from natural quiet. Phase 2 model sees uniform "this region is silence" rather than a discontinuity. |
| Zero | Bad. Zero in log-mel space corresponds to power=1, which is loud. Creates a step function the model has to learn to ignore. |
| Replicate last frame | Bad. Smears trailing transient indefinitely; model can't tell where audio ended. |
| Mean of frame | Bad. Smears spectral centroid; loses silence cue. |

[VERIFIED via torchaudio docs: power=2.0 means the output is squared magnitude, log of which is roughly proportional to dB; a log floor of -18.4 corresponds to about -80 dB, which is well below any meaningful FM signal.]

**Frame-count sanity check:** 22050 Hz / 512 hop ≈ 43.07 frames/sec. 96 frames × 1/43.07 ≈ 2.23 s. With `center=True`, MelSpectrogram pads internally so the frame count equals `1 + (samples // hop)`. A 1.5 s call = 33075 samples → 1 + 33075/512 ≈ 65 frames → padded to 96. A 2.2 s call → ~95 frames → padded to 96 by 1. ✓

## Pre-tokenized Artifact Schema

### Format: a single `.pt` file via `torch.save`, containing a dict of tensors + metadata.

```python
# Schema (the dict structure saved to disk):
{
    "schema_version": 1,                # int — bump if format changes
    "vocab": {                          # Mirror of Vocab dataclass — frozen at ingest time
        "PITCH_MIN": 36, "PITCH_MAX": 72, "N_PITCH": 37,
        "N_TIME": 32, "N_VELOCITY": 16, "N_DURATION": 24,
        "TIME_OFFSET": 0, "PITCH_OFFSET": 32,
        "VELOCITY_OFFSET": 69, "DURATION_OFFSET": 85,
        "BOS": 109, "EOS": 110, "SEP": 111,
        "VOCAB_SIZE": 256, "ACTIVE_VOCAB": 112,
        "tempo_bpm": 120.0,
        "duration_edges": [...],         # 25 floats for round-trip reconstruction
    },
    "mel_config": {
        "sample_rate": 22050,
        "n_fft": 2048, "hop_length": 512, "n_mels": 128,
        "target_frames": 96,
        "log_floor": 1e-8,
    },
    "pairs": [                          # list of length N (one per pair on disk)
        {
            "nnn": "001",                # string, preserves any zero-padding
            "is_heldout": False,         # bool, from hash split
            "call_tokens": Tensor(shape=(Lc,), dtype=int32),    # variable length
            "response_tokens": Tensor(shape=(Lr,), dtype=int32),
            "call_mel": Tensor(shape=(96, 128), dtype=float32),
        },
        ...
    ],
    "metadata": {
        "ingest_timestamp": "2026-05-19T15:30:00Z",
        "source_root": "data/pairs",
        "n_pairs": N,
        "n_heldout": M,
        "apollo_version": "0.1.0",      # from apollo.__version__
    },
}
```

**Dtypes:**
- Tokens: `int32` — fits the full 256 vocab with room; cheap to upcast to int64 in DataLoader if model needs it.
- Mel: `float32` — matches torchaudio default; no benefit from float16 at ingest time, model can cast.

**Why this format (not HDF5, not Parquet, not Arrow):**

| Option | Verdict |
|--------|---------|
| **`.pt` dict-of-tensors via `torch.save`** | **CHOSEN.** Native, zero extra deps, schema-flexible (just add keys), `torch.load` returns the dict in one line. Phase 2 DataLoader wraps it in a custom `Dataset` that indexes `data["pairs"][i]`. Pickle-based — fine for our trust model (we wrote the file). |
| HDF5 (`h5py`) | Overkill at this scale (≤200 pairs). Adds a binary-format dep, complicates inspection. Wins only with random-access or memory-mapped datasets we don't need. |
| Parquet / Arrow | Tabular formats; awkward fit for nested tensors of varying length. Adds heavy deps. |
| One file per pair | Slow at DataLoader init (filesystem hits); fragments the schema definition across files. |

**Schema evolution policy:** Bump `schema_version` on any breaking change. Phase 2's loader asserts `data["schema_version"] == 1` (or accepts versions it knows). Non-breaking additions (new metadata keys) don't bump the version.

## Deterministic Split

### Function

```python
# apollo/ingest/split.py
import hashlib

def normalize_nnn(nnn: str) -> str:
    """
    Canonical form for NNN strings before hashing.
    Strips whitespace, lowercases (no-op for digits but defensive), preserves leading zeros.
    """
    s = nnn.strip().lower()
    if not s:
        raise ValueError(f"empty NNN string")
    return s

def is_heldout(nnn: str, k: int = 5) -> bool:
    """
    Returns True if pair NNN is in the held-out (eval) split.
    20% split when k=5. Stable across runs, immune to authoring order.
    """
    s = normalize_nnn(nnn)
    h = int(hashlib.sha1(s.encode("utf-8")).hexdigest(), 16)
    return (h % k) == 0
```

### Pitfalls and mitigations

| Pitfall | Mitigation |
|---------|------------|
| **Leading-zero inconsistency**: hashing "001" vs "1" gives different splits | Normalize uses `s.strip().lower()` but **preserves zero padding** — the folder name is the canonical key. If the user has folders `001/`, `002/`, ..., always use those exact strings. Document in code: "We hash the directory name as-is, modulo whitespace strip." |
| **Encoding ambiguity**: hashing the str vs the bytes | Explicit `.encode("utf-8")`. |
| **Whitespace / trailing newline**: a filesystem walk might produce "001\n" on some platforms | `.strip()` covers this. |
| **Cross-platform path quirks**: Windows would join paths with backslashes (we're on macOS — but defensive) | Hash only the directory basename, never the full path. |
| **20% drift on small N**: With 10 pairs, 20% expected = 2 but actual could be 1 or 3 due to hash chunking | Acceptable — `DATA-04` says "20% deterministic," not "exactly 20% every count." With N=30+ the variance is ≤1 pair from expected. |
| **k=5 means exactly 20% only in expectation** | Documented behavior. If user wants different ratio later, expose k as a parameter — already supported in the signature. |

### Determinism guarantees

- `sha1` is deterministic across Python versions, platforms, and time. [VERIFIED: Python stdlib]
- Adding a new pair never changes the split assignment of existing pairs.
- Renaming a pair (e.g. `001/` → `031/`) **does** change its split — that's the right behavior (it's a new identity).

## Error Handling

### Pattern: typed exception with pair path + reason

```python
# apollo/ingest/errors.py
class IngestError(Exception):
    """
    Raised on any pair-level ingest failure (D-04, D-16, COND-04).
    Carries the offending pair path so the user can fix the file directly.
    """
    def __init__(self, pair_path: str, reason: str):
        self.pair_path = pair_path
        self.reason = reason
        super().__init__(f"[{pair_path}] {reason}")
```

### Call sites

| Failure mode | Where raised | Message |
|--------------|--------------|---------|
| Missing `call.mid` | `pairs.py` | "missing call.mid" |
| Missing `call.wav` | `pairs.py` | "missing call.wav" |
| Missing `response.mid` | `pairs.py` | "missing response.mid" |
| Malformed MIDI file | `midi.py` | "failed to parse <path>: <pretty_midi error>" |
| Malformed WAV file | `audio.py` | "failed to load <path>: <torchaudio error>" |
| Pitch out of range | `encoder.py` | "pitch <N> outside C2-C5 window (allowed: 36-72)" |
| Overlapping notes (polyphony) | `midi.py` | "overlapping notes — corpus is monophonic" |
| Time gap > 32 bins | `encoder.py` | "time_shift <X.XXX>s exceeds vocab range (max <Y.YYY>s)" |
| Empty NNN string / unparseable folder name | `pairs.py` | "could not parse NNN from folder name" |
| Mel n_mels mismatch (defensive) | `audio.py` | "mel produced N mels, expected 128" |

### Top-level CLI behavior

```python
# apollo/scripts/ingest_corpus.py
def main():
    try:
        artifact = ingest(args.pairs_root)
        save_artifact(artifact, args.output)
        print(f"OK: {artifact['metadata']['n_pairs']} pairs → {args.output}")
        sys.exit(0)
    except IngestError as e:
        print(f"INGEST FAILED: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"UNEXPECTED ERROR: {e!r}", file=sys.stderr)
        sys.exit(2)
```

**Exit codes:**
- `0`: Success.
- `1`: Pair-level `IngestError` — known failure with offending pair identified.
- `2`: Anything else (unexpected exception) — bug or environment issue.

Distinguishing these matters: in CI / iteration, exit 1 is "the corpus has a bad pair, go fix it." Exit 2 is "the tool is broken." Bare `RuntimeError` would conflate them.

## Round-Trip Test

### Strategy

Generate a sequence of mock `Note` objects with **known, simple values** that align cleanly to the quantization grid → encode → decode → assert each field matches within tolerance.

**Why mock notes (not mock MIDI files):** the round-trip test should isolate the tokenizer. Going through file I/O adds pretty_midi's tick → seconds conversion as a confounder. Separate test (`test_ingest_smoke.py`) covers the file path.

### Tolerances

| Field | Tolerance | Justification |
|-------|-----------|---------------|
| **Pitch** | **0 (exact)** | Pitch bins are integer MIDI numbers, no quantization within a bin. If pitch round-trips wrong, the encoder has a bug. |
| **Velocity** | **±4 MIDI units (out of 127)** | 16 velocity bins means each bin spans 127/16 ≈ 8 units. Half-width = 4. A value of 64 might decode as 60 or 68 (bin center). |
| **Onset time** | **±10 ms** | At 120 bpm, 32 bins over 2 beats = 1 sec / 32 ≈ 31 ms per bin. Half-bin = ~15 ms. 10 ms tolerance is tighter (we choose mock inputs that fall mid-bin). |
| **Duration** | **±19% (relative)** | Log-spaced bin ratio. A 100 ms note decoded to its bin center could be anywhere in [91 ms, 109 ms]. Test asserts `abs(actual - expected) / expected < 0.19`. |

### Concrete test structure

```python
# tests/test_tokenizer_roundtrip.py
import pytest
from apollo.tokenizer import Tokenizer, Vocab, Note

PITCH_TOL = 0
VELOCITY_TOL = 4
ONSET_TOL_SEC = 0.010
DURATION_TOL_REL = 0.19

@pytest.fixture
def tokenizer():
    return Tokenizer(vocab=Vocab(), tempo_bpm=120.0)

def test_single_note_round_trip(tokenizer):
    """A single C4 quarter note at velocity 64 round-trips."""
    notes_in = [Note(pitch=60, velocity=64, start=0.0, end=0.5)]
    ids = tokenizer.encode(notes_in)
    assert len(ids) == 4
    notes_out = tokenizer.decode(ids)
    assert len(notes_out) == 1
    assert notes_out[0].pitch == 60
    assert abs(notes_out[0].velocity - 64) <= VELOCITY_TOL
    assert abs(notes_out[0].start - 0.0) <= ONSET_TOL_SEC
    expected_dur = 0.5
    actual_dur = notes_out[0].end - notes_out[0].start
    assert abs(actual_dur - expected_dur) / expected_dur <= DURATION_TOL_REL

def test_six_note_phrase(tokenizer):
    """A 6-note phrase across the pitch range round-trips."""
    notes_in = [
        Note(pitch=36, velocity=40,  start=0.000, end=0.125),  # C2
        Note(pitch=48, velocity=64,  start=0.125, end=0.250),  # C3
        Note(pitch=60, velocity=80,  start=0.375, end=0.500),  # C4
        Note(pitch=64, velocity=96,  start=0.500, end=0.625),  # E4
        Note(pitch=67, velocity=110, start=0.750, end=1.000),  # G4
        Note(pitch=72, velocity=120, start=1.000, end=1.500),  # C5
    ]
    notes_out = tokenizer.decode(tokenizer.encode(notes_in))
    assert len(notes_out) == len(notes_in)
    for ni, no in zip(notes_in, notes_out):
        assert no.pitch == ni.pitch
        assert abs(no.velocity - ni.velocity) <= VELOCITY_TOL
        assert abs(no.start - ni.start) <= ONSET_TOL_SEC
        dur_in = ni.end - ni.start
        dur_out = no.end - no.start
        assert abs(dur_out - dur_in) / dur_in <= DURATION_TOL_REL

def test_pitch_out_of_range_aborts(tokenizer):
    notes = [Note(pitch=24, velocity=64, start=0.0, end=0.5)]  # below C2
    with pytest.raises(IngestError, match="outside"):
        tokenizer.encode(notes)
```

**Coverage check** for TOK-05: pitches preserved exactly ✓, velocities within 4 (bin width) ✓, onsets within 10 ms ✓, durations within 19% (log bin width) ✓. The phrase test exercises every part of the encode/decode loop. Out-of-range test covers D-04.

## Mock Pair Generation

### Strategy

For pipeline tests we need a `data/pairs/000-test/` (or similar) folder containing valid `call.mid`, `call.wav`, `response.mid`. Generating real Ableton-rendered Operator audio is infeasible in CI — but we don't need it. The mel encoder is jointly trained (Phase 2), so the mock wav just needs to be a valid audio file of plausible length. **A short sine sweep or silence is fine.**

```python
# apollo/ingest/mock.py
import numpy as np
import pretty_midi
import torchaudio
import torch
from pathlib import Path

def synthesize_pair(out_dir: Path, nnn: str = "000",
                    call_pitches=(60, 62, 64), call_durs=(0.25, 0.25, 0.25),
                    response_pitches=(67, 65, 64), response_durs=(0.25, 0.25, 0.25),
                    audio_sr: int = 44100, audio_seconds: float = 1.0):
    """Write data/pairs/{nnn}/{call.mid, call.wav, response.mid} for tests."""
    pair_dir = out_dir / nnn
    pair_dir.mkdir(parents=True, exist_ok=True)

    def write_midi(path: Path, pitches, durations, velocity=80):
        pm = pretty_midi.PrettyMIDI(initial_tempo=120.0)
        inst = pretty_midi.Instrument(program=0)
        t = 0.0
        for p, d in zip(pitches, durations):
            inst.notes.append(pretty_midi.Note(velocity=velocity, pitch=p, start=t, end=t+d))
            t += d
        pm.instruments.append(inst)
        pm.write(str(path))

    write_midi(pair_dir / "call.mid", call_pitches, call_durs)
    write_midi(pair_dir / "response.mid", response_pitches, response_durs)

    # Synthesize a simple sine-tone wav matching call pitches (good enough for pipeline test)
    t = np.arange(int(audio_seconds * audio_sr)) / audio_sr
    # 440 Hz tone, mono — content doesn't matter, just shape/format
    wav = 0.1 * np.sin(2 * np.pi * 440 * t).astype(np.float32)
    wav_tensor = torch.from_numpy(wav).unsqueeze(0)  # (1, samples)
    torchaudio.save(str(pair_dir / "call.wav"), wav_tensor, audio_sr)

    return pair_dir
```

**Acceptable for tests:**
- Silence (all-zero wav). Even simpler — log_mel becomes the floor value everywhere; mel extraction must still produce `(96, 128)`.
- 440 Hz sine. Slightly more realistic content; useful for sanity-checking mel pipeline produces non-floor values.
- Filtered noise. If you want richer spectral content; overkill for the smoke test.

**NOT acceptable for tests:**
- A real Ableton Operator render. Test environment can't run Ableton. Real audio is the user's job (DATA-01).
- Skipping the audio file entirely. The pipeline must read a wav; "no wav" is the error-path test, not the happy-path test.

**Use cases:**
1. `test_ingest_smoke.py` — generate 5 mock pairs, run full ingest, assert artifact has 5 entries with correct shapes.
2. `test_error_handling.py` — generate a pair, delete `call.wav`, assert `IngestError` raised.
3. Phase 2 smoke train (TRAIN-04) — generate ≥10 mock pairs as the training corpus.

## Open Risks

Items CONTEXT.md left ambiguous or that the planner needs to surface:

1. **Tempo assumption is hardcoded.** [ASSUMED] `tempo_bpm=120.0` in the tokenizer defines the time-bin width. If the user authors a pair at a different tempo, the time quantization will misalign. CONTEXT.md doesn't address this — D-05 says "at the corpus tempo" but doesn't specify how the tempo is communicated. **Recommendation:** the tokenizer accepts `tempo_bpm` at construction; the ingest pipeline either (a) hardcodes 120 for v1 and documents the constraint, or (b) reads tempo from the MIDI file's tempo marker (`pretty_midi.PrettyMIDI.estimate_tempo()`). Option (a) is simpler and matches a corpus authored at one tempo. **Surface for discussion in plan-check.**

2. **What if `response.mid` has notes outside C2–C5?** D-04 says pitch out of range during ingest → abort. But responses are model output in Phase 3 — should the tokenizer's encoder reject out-of-range pitches even when re-encoding for round-trip validation? **Recommendation:** Yes, treat call and response symmetrically. Phase 1 only encodes (not decodes-then-re-encodes), so this only matters if response.mid as authored has out-of-range pitches — which should abort.

3. **MIDI tempo marker in `call.mid` ignored.** The tokenizer doesn't use `pretty_midi`'s tempo info — it uses its own configured `tempo_bpm`. If the user changes tempo mid-corpus, time bins will misalign for the new pairs. **Recommendation:** Plan a guard: at ingest time, read each MIDI's tempo (`pm.estimate_tempo()`) and assert it equals the tokenizer's configured tempo within ±2 bpm. Else, abort with offending pair.

4. **Mel `power=2.0` vs `power=1.0`** [ASSUMED]. CONTEXT.md specifies n_mels, n_fft, hop, but not whether to use power or magnitude spectrogram. Default in torchaudio is `power=2.0` (power). Log of power is roughly dB-scaled. The choice changes the dynamic range of `log_mel` inputs to the Phase 2 encoder. **Recommendation:** Use `power=2.0` (the default) — standard in most MIR work. Document this; Phase 2 may want to revisit if dynamics are mushy.

5. **Time-shift "bin 0" semantics.** In monophonic v1, every note has a strictly positive `time_shift` from the previous note (no chord onsets). Bin 0 (zero time shift) is unused. The encoder could either (a) emit bin 0 for the very first note (start at t=0), or (b) special-case the first note. **Recommendation:** Emit bin 0 for the first note. Simpler, no special case. Decoder reads bin 0 as "no advance," cursor stays at 0. Fully consistent.

6. **Empty MIDI files.** What if `call.mid` has zero notes (a rest)? D-16's policy is missing/malformed → abort. Is an empty-but-valid MIDI "malformed"? **Recommendation:** Treat as IngestError with reason "no notes in call.mid". Useful music can't be a 0-token sequence; if user authored an empty pair it's a mistake.

7. **What `pretty_midi` instrument to read.** Both `call.mid` and `response.mid` should have exactly one instrument track. **Recommendation:** Assert `len(pm.instruments) == 1` at load time. If multi-track authoring becomes a thing, add a track-selection arg later.

8. **Held-out pair count when N is small.** With < 10 pairs, the hash modulo could produce 0 held-out pairs by chance. **Recommendation:** No special handling in Phase 1 — DATA-05 requires ≥30 pairs before the first real training run, and the smoke train uses mock pairs where determinism matters less. The ingest pipeline should log `n_heldout` count; if zero, that's the user's signal to author more.

9. **Artifact path / location convention.** [ASSUMED] CONTEXT.md doesn't specify where the `.pt` artifact lives. **Recommendation:** `artifacts/tokenized_v1.pt` at the repo root (gitignored). Phase 2 reads from there by default. Surfaces a small `--output` CLI arg for override.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `pyproject.toml` + setuptools is appropriate; user is okay with this vs. `uv` / `poetry` / requirements.txt | Module Layout | Low — easy to swap, planner can ask |
| A2 | Mel `power=2.0` is preferable to `power=1.0` (magnitude) | Open Risks #4 | Low — Phase 2 can change without breaking Phase 1 |
| A3 | Tempo 120 bpm is the corpus tempo (or close enough) | Tokenizer Design | Medium — if user authors at different tempo, time bins misalign |
| A4 | Artifact path `artifacts/tokenized_v1.pt` at repo root | Open Risks #9 | Low — just a path convention |
| A5 | 24 duration bins is the right point on the 16–32 spectrum | Duration Bin Scheme | Low — well-reasoned per Weber's law, but planner / user may prefer 16 or 32 |
| A6 | Padding value `log(1e-8)` is preferable to zero for fixed-shape mel | Mel Pipeline | Low — defensible; can change without breaking schema |
| A7 | `pretty_midi` is available locally (verified) and on any future install target | Library Recommendations | Very low — verified installed, standard package |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | All | ✓ | 3.9.6 (system); venv exists | — |
| torch | Tensor I/O, artifact format | ✓ (in venv) | 2.8.0 | — |
| torchaudio | Resample, MelSpectrogram, wav load | ✓ (in venv) | 2.8.0 | librosa (NOT recommended) |
| pretty_midi | MIDI parse + write | ✓ (in venv) | 0.2.11 | mido (more boilerplate) |
| numpy | Bin edges, math | ✓ (in venv) | 2.0.2 | — |
| librosa | (alternative mel) | ✓ (in venv) | 0.11.0 | — (not used in recommended design) |
| pytest | Tests | not verified | — | unittest (stdlib, more boilerplate) |
| MPS (Apple Silicon GPU) | Phase 2 only | ✓ (presumed; user is on macOS) | — | — (Phase 1 is CPU-only, no MPS needed) |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** `pytest` may need `pip install pytest`. Verify before planning.

## Code Examples

### MIDI load (verified pattern)

```python
import pretty_midi
pm = pretty_midi.PrettyMIDI("data/pairs/001/call.mid")
assert len(pm.instruments) == 1, "monophonic single-track only"
notes = pm.instruments[0].notes   # list of pretty_midi.Note(pitch, velocity, start, end)
# notes are NOT sorted by start in pretty_midi — sort yourself:
notes.sort(key=lambda n: n.start)
```
[CITED: https://craffel.github.io/pretty-midi/]

### MIDI write (for decoder output + mock generation)

```python
pm = pretty_midi.PrettyMIDI(initial_tempo=120.0)
inst = pretty_midi.Instrument(program=0)
for note in decoded_notes:
    inst.notes.append(pretty_midi.Note(
        velocity=note.velocity, pitch=note.pitch,
        start=note.start, end=note.end,
    ))
pm.instruments.append(inst)
pm.write("response.mid")
```

### Mel pipeline (verified pattern)

```python
import torchaudio
import torch
wav, sr = torchaudio.load("call.wav")
if wav.shape[0] > 1:
    wav = wav.mean(dim=0, keepdim=True)
if sr != 22050:
    wav = torchaudio.transforms.Resample(sr, 22050)(wav)
mel = torchaudio.transforms.MelSpectrogram(
    sample_rate=22050, n_fft=2048, hop_length=512, n_mels=128,
)(wav)
log_mel = torch.log(mel + 1e-8).squeeze(0).transpose(0, 1)
```
[CITED: https://docs.pytorch.org/audio/main/generated/torchaudio.transforms.MelSpectrogram.html]

### Hash-based split (verified deterministic)

```python
import hashlib
def is_heldout(nnn: str) -> bool:
    h = int(hashlib.sha1(nnn.strip().encode("utf-8")).hexdigest(), 16)
    return (h % 5) == 0
# Tested: is_heldout("001"), is_heldout("002"), ... gives a deterministic 20% subset
```

### Save / load artifact

```python
import torch
# Save
torch.save(artifact_dict, "artifacts/tokenized_v1.pt")
# Load (in Phase 2)
data = torch.load("artifacts/tokenized_v1.pt", map_location="cpu", weights_only=False)
assert data["schema_version"] == 1
for entry in data["pairs"]:
    nnn, call_toks, resp_toks, mel = entry["nnn"], entry["call_tokens"], entry["response_tokens"], entry["call_mel"]
```

## Common Pitfalls

### Pitfall 1: Notes returned by pretty_midi are not start-sorted
**What goes wrong:** Encoder assumes notes are in time order; if not, time_shifts go negative and abort.
**Why it happens:** pretty_midi preserves the order in the MIDI file, which depends on the authoring DAW's track ordering.
**How to avoid:** Always `notes.sort(key=lambda n: n.start)` after loading. Document in `midi.py`.

### Pitfall 2: `torchaudio.load` returns shape `(channels, samples)`, not `(samples,)`
**What goes wrong:** Code that expects 1D waveform breaks on stereo or fails silently on mono (gets a leading dimension).
**Why it happens:** torchaudio's tensor convention.
**How to avoid:** Always `wav = wav.mean(dim=0, keepdim=True)` to mono-mix. Keep the leading dim — MelSpectrogram expects `(..., samples)`.

### Pitfall 3: `MelSpectrogram` with `center=True` adds reflection padding
**What goes wrong:** Frame count is `1 + (samples // hop)`, not `samples // hop`. Off-by-one when computing expected frame counts.
**Why it happens:** `center=True` is the default and matches librosa convention.
**How to avoid:** Use `_fix_frames` to pad/truncate to a known target. Don't try to compute exact frame counts upstream.

### Pitfall 4: `torch.save` with PyTorch 2.6+ defaults to `weights_only=True` on load
**What goes wrong:** Loading a dict-of-tensors with `torch.load(path)` may warn or fail in newer versions.
**Why it happens:** PyTorch added a security default in 2.6.
**How to avoid:** Always load with `torch.load(path, weights_only=False)` for our dict artifact (we trust our own file). [VERIFIED: torch 2.8 in venv — applies here.]

### Pitfall 5: Hash collision in tiny corpora
**What goes wrong:** With N=5 pairs, all 5 might hash to non-heldout (probability ~32%). Pipeline runs but with 0 eval pairs.
**Why it happens:** Statistics of `mod 5`.
**How to avoid:** Just log `n_heldout` at ingest; user will see "0 held-out pairs" and author more. Not a Phase 1 bug.

### Pitfall 6: pretty_midi's `Note.start` and `Note.end` are floats in seconds, but MIDI files store ticks
**What goes wrong:** Tiny floating-point errors (e.g., `start=0.49999999` instead of `0.5`) make duration just under a bin boundary, decoding to wrong bin.
**Why it happens:** Tick → seconds conversion is via `tick / resolution * (60 / tempo)`.
**How to avoid:** All quantization functions should round-to-nearest, not floor/ceil. `np.searchsorted` with `side='right'` already handles boundary cases consistently.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| MIDI file parsing | Custom mido NoteOn/NoteOff matcher | `pretty_midi` | Edge cases: simultaneous notes, missing NoteOff (= 0-vel NoteOn), pedal events. Already solved. |
| Audio resampling | Manual scipy.signal.resample_poly | `torchaudio.transforms.Resample` | Polyphase filter design, anti-aliasing, edge handling. Done correctly. |
| Mel filterbank | Manual STFT + triangle mel filters | `torchaudio.transforms.MelSpectrogram` | HTK vs Slaney scale conventions, FFT windowing, framing. Done correctly. |
| Hash-based deterministic split | Random with seed | `hashlib.sha1(nnn) % k` | Seeded random depends on call order; hash split depends only on the key. The latter is robust to corpus growth. |
| Serialization | Custom binary format | `torch.save` | Pickle-based, native, zero deps, handles tensors transparently. |
| Tempo / time-signature math | Custom seconds-per-bin math | Hardcode 120 bpm initially, derive bin width from `60.0 / bpm / 8.0` | Tempo flexibility is a Phase 2+ concern; not worth abstracting now. |

**Key insight:** This phase is heavy on bespoke logic (vocab IDs, bin edges, error policy) but should use third-party libraries everywhere there's a standard solution. Hand-rolling MIDI or audio I/O wastes time on solved problems and introduces bugs that only show up months later on edge-case files.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| NoteOn / NoteOff event pairs | Explicit duration tokens | ~2018 (Music Transformer era) | Smaller sequence length (4 tokens/note vs ~3 events/note with NoteOff), simpler model attention |
| Variable-length mel | Fixed-length mel with pad/truncate | Standard since ~2020 | Enables batching without masking; matches Phase 1's encoder contract |
| `librosa` for mel | `torchaudio` for mel | ~2021 onwards (torchaudio matured) | Native torch tensors, faster, MPS-compatible |
| Magic constants in code | Frozen dataclass / config dict | Always preferred | Vocab is self-documenting; checkpoints can store the vocab struct |

**Deprecated/outdated:**
- Using MIDI NoteOff events as tokens: replaced by explicit duration tokens (per D-07).
- Variable-length mel with attention masks: deferred per D-13 (fixed shape locked).

## Sources

### Primary (HIGH confidence)
- pretty_midi documentation: https://craffel.github.io/pretty-midi/ — Note class signature, instrument/note access patterns
- torchaudio MelSpectrogram docs: https://docs.pytorch.org/audio/main/generated/torchaudio.transforms.MelSpectrogram.html — Signature, defaults, output shape
- Installed venv (verified versions): `torch 2.8.0`, `torchaudio 2.8.0`, `pretty_midi 0.2.11`, `librosa 0.11.0`, `numpy 2.0.2`
- Python stdlib `hashlib` — deterministic across versions [VERIFIED]

### Secondary (MEDIUM confidence)
- General MIR conventions for n_fft=2048, hop=512, n_mels=128 — standard across literature, verified default in Beat This! (ISMIR 2024) using `n_fft=1024, hop=441` confirms these are the right family of parameters

### Tertiary (LOW confidence)
- Weber-fraction argument for 19% duration bin spacing — psychoacoustic reasoning, not formally cited [ASSUMED reasonable]
- 144-slot reservation tail is "generous enough" for v2 — projection only, not based on a concrete v2 spec [ASSUMED]

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — verified installed, well-documented APIs
- Architecture: HIGH — conventional layout, no novel patterns
- Pitfalls: HIGH — documented torchaudio / pretty_midi quirks
- Duration bin design: MEDIUM — choice of 24 is reasoned but not empirically validated; could be 16 or 32 with similar results
- Tempo assumption: LOW — hardcoded 120 bpm needs user confirmation in plan-check

**Research date:** 2026-05-19
**Valid until:** 2026-06-19 (30 days; stable libraries, no fast-moving dependencies)

## RESEARCH COMPLETE

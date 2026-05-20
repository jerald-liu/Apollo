# Phase 1: Tokenizer & Ingest - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-19
**Phase:** 01-tokenizer-ingest
**Areas discussed:** Tokenizer vocab structure, Mel spectrogram parameters

---

## Tokenizer vocab structure

### Round 1

#### Pitch range — what slice of MIDI 0–127 should the vocab cover?

| Option | Description | Selected |
|---|---|---|
| Full 0–127 (128 pitches) | All MIDI pitches. Maximum flexibility, future-proof for any Operator preset. Larger vocab. | |
| Piano range 21–108 (88 pitches) | A0 to C8. Narrower vocab. Cleaner if you never venture outside piano range. | |
| Centered range 24–96 (73 pitches) | C1 to C7. Common synth/lead range. Smallest of the three; cuts off sub-bass and screech zones. | |
| (Other — free text) | | ✓ |

**User's choice:** *"We won't have a huge range. probably within 2-3 octaves max for now. 'screeches' will be encoded as overtones of a lower fundamental (for later)"*
**Notes:** Reframed the problem — FM synthesis does timbre/overtone work, so the MIDI vocab can stay narrow even when the *output sound* covers many octaves. This is architecturally load-bearing (captured as D-03).

#### Time-shift encoding — quantized grid bins or log-spaced bins?

| Option | Description | Selected |
|---|---|---|
| Fixed quantized grid (e.g. 32 bins = 32nd notes for 1 bar) | Coarse, evenly-spaced bins matching musical subdivisions. Cleanest for v1. | ✓ |
| Log-spaced bins (e.g. 64 bins, log from 1ms to 2s) | Finer resolution at short deltas. Better when groove/free timing arrives later. | |
| Hybrid: 32 grid bins now + reserved range for log bins later | Grid bins now, reserve token IDs for log-bin tokens to be added later. | |

**User's choice:** *"Quantized for now. later introducing groove/delay/'free timing'"*
**Notes:** Combined with the extensibility choice below, this becomes the hybrid in spirit — quantized v1 + reserved tail slots for later expression/timing tokens.

#### Velocity bin count — how many discrete levels?

| Option | Description | Selected |
|---|---|---|
| 16 bins (4-bit resolution) | Coarse but plenty for a small corpus. Less risk of unused tokens. | ✓ |
| 32 bins (5-bit resolution) | Common middle ground. | |
| 8 bins (3-bit) | Very coarse. Safe but may flatten authored velocity nuance. | |

**User's choice:** 16 bins (4-bit resolution)
**Notes:** —

#### Vocab extensibility scheme — how to reserve room for pitch bend / mod wheel / CC tokens later?

| Option | Description | Selected |
|---|---|---|
| Reserved contiguous slots at end of vocab | Pack today's vocab into 0..N-1; reserve N..(N+K-1) for v2 tokens. Existing checkpoints stay compatible. | ✓ |
| Versioned vocab tag in token-0 | Token at position 0 encodes vocab version. Heavier-handed; more brittle. | |
| Generous overallocation upfront | Allocate ~1024 IDs from day one, most unused. Simplest; wastes some embedding parameters. | |

**User's choice:** Reserved contiguous slots at end of vocab
**Notes:** Lines up with the time-shift extension plan — same reservation strategy.

### Round 2 (follow-ups)

#### Which 3-octave window for the pitch vocab? (~37 pitches)

| Option | Description | Selected |
|---|---|---|
| C2–C5 (MIDI 36–72) | Bass through mid-treble. Most common synth-lead/bassline territory. | |
| C3–C6 (MIDI 48–84) | Centered higher — leads, melodic, vocal-adjacent. | |
| F1–F4 (MIDI 29–65) | Centered lower — bass-heavy, sub-bass-friendly. | |
| I'll decide later — use C2–C5 as default and widen/shift if needed | Author the corpus first, then revisit. | ✓ |

**User's choice:** Defer — use C2–C5 as default for now
**Notes:** Captured as D-02 + a Deferred Idea. The corpus authoring will reveal where the pitch window actually needs to be.

#### How many time-shift bins for the quantized grid?

| Option | Description | Selected |
|---|---|---|
| 32 bins (32nd-note grid over ~2 beats) | Resolves down to ~60ms at 120bpm. Covers most tiny-gesture deltas. | ✓ |
| 16 bins (16th-note grid over ~2 beats) | Coarser — ~125ms minimum. Saves vocab slots. | |
| 64 bins (32nd-note grid over ~4 beats) | More headroom for longer gaps. Slight vocab cost. | |

**User's choice:** 32 bins
**Notes:** —

#### Duration encoding — explicit duration token, or note-on/note-off pairs?

| Option | Description | Selected |
|---|---|---|
| Explicit duration token per note | 4 tokens per note (time_shift, pitch, velocity, duration). Concise for monophonic. | ✓ |
| Note-on / note-off pairs | Separate token for releasing each note. More verbose for monophonic. | |
| No duration token (fixed duration) | Cheapest but loses authored note length. Bad for FM. | |

**User's choice:** Explicit duration token per note
**Notes:** —

---

## Mel spectrogram parameters

#### Sample rate for mel feature extraction

| Option | Description | Selected |
|---|---|---|
| 22050 Hz (librosa default) | Nyquist 11kHz captures FM harmonics. Half the cost of 44.1k. | ✓ |
| 16000 Hz (speech-style) | Nyquist 8kHz — cuts off real FM brightness above 8kHz. | |
| 44100 Hz (full Ableton output) | No downsampling. Doubles audio-side compute. | |

**User's choice:** 22050 Hz
**Notes:** —

#### Mel resolution — frequency bins and time hop

| Option | Description | Selected |
|---|---|---|
| n_mels=128 · n_fft=2048 · hop=512 | Industry-standard music preset. ~43 frames/sec. | ✓ |
| n_mels=64 · n_fft=1024 · hop=256 | Compact. ~86 fps but only 64 mel bins. | |
| n_mels=256 · n_fft=2048 · hop=256 | High resolution. 4× the data of recommended. | |

**User's choice:** n_mels=128 · n_fft=2048 · hop=512
**Notes:** —

#### Fixed-shape or variable-length mel tensor going into the encoder?

| Option | Description | Selected |
|---|---|---|
| Fixed-shape (pad/truncate to N frames) | One tensor shape for every pair. Easy to batch. | ✓ |
| Variable-length with attention masking | Encoder handles whatever length. More flexible, adds masking complexity. | |
| Pool to a fixed-length embedding inside the encoder | Encoder takes variable input, outputs fixed embedding. Loses temporal structure. | |

**User's choice:** Fixed-shape
**Notes:** Claude set N=96 frames (~2.23s at 43 fps) as the default to give ~50% headroom over the 1.5s max gesture length. Captured as D-13.

---

## Claude's Discretion

The user explicitly did not want to discuss:
- **Held-out split policy** — Claude defaulted to hash-based 20% split (D-20).
- **Pipeline output / storage format** — Claude defaulted to pre-tokenized `.pt` artifact (D-18/19).

Captured as locked decisions in CONTEXT.md rather than as open Claude-discretion items, because both have clear-cut best practices for this scope and revisiting them would only matter on failure.

## Deferred Ideas

- Exact 3-octave pitch window — revisit after authoring the corpus
- Pitch-shift augmentation — Phase 2 concern
- Pitch bend / mod wheel / CC tokens — v2 (vocab slots reserved only)
- Groove / free / off-grid timing tokens — v2 (reservation-level only)
- Variable-length mel input — future option if fixed-shape bites
- Mel normalisation strategy beyond log-mel — defer to Phase 2

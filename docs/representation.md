# Apollo Event Representation

## Design Goals

1. **Rich enough** to capture pitch, velocity, timing, duration, pedal, and timbral descriptors
2. **Compact enough** for real-time inference at <20ms per step
3. **Instrument-agnostic** at the representation level (piano-specific perception is a separate layer)
4. **Not hardcoded to Western harmony** — no built-in chord vocabularies or scale degree assumptions

## The Apollo Event

Each musical event is a vector with the following fields:

### Core Fields (always present)

| Field | Encoding | Range | Notes |
|---|---|---|---|
| `pitch` | Integer | 0–127 | MIDI pitch. 0 = rest/silence |
| `velocity` | Float | 0.0–1.0 | Normalized from MIDI 0–127 |
| `onset` | Float | seconds | Absolute time or relative to bar start |
| `duration` | Float | seconds | Note length (onset to offset) |
| `delta_time` | Float | seconds | Time since previous event (for autoregressive generation) |

### Expressive Fields

| Field | Encoding | Range | Notes |
|---|---|---|---|
| `pedal_sustain` | Float | 0.0–1.0 | Sustain pedal state (continuous, not binary) |
| `pedal_soft` | Float | 0.0–1.0 | Soft/una corda pedal state |
| `articulation` | Float | 0.0–1.0 | Ratio of sounding duration to IOI. 0=staccato, 1=legato |

### Timbral Descriptors (Apollo's extension beyond SongDriver)

| Field | Encoding | Range | Notes |
|---|---|---|---|
| `brightness` | Float | 0.0–1.0 | Spectral centroid (normalized). Maps to synth filter cutoff |
| `attack` | Float | 0.0–1.0 | Attack sharpness. 0=soft onset, 1=percussive. Maps to amp envelope |
| `richness` | Float | 0.0–1.0 | Spectral flatness / harmonic density. Maps to oscillator mix |
| `warmth` | Float | 0.0–1.0 | Inverse spectral rolloff. Low rolloff = warm/bass-heavy. Maps to tone |
| `flux` | Float | 0.0–1.0 | Spectral change rate. High = vibrato/tremolo. Maps to modulation |

These timbral descriptors are **output-side only** in Phase 1 (MIDI input doesn't carry timbre info).
They represent what Apollo *wants* the response to sound like. Mapped to MIDI CC messages
for synth parameter control. Derived from FFT analysis of paired MAESTRO audio when
`--spectral` preprocessing is enabled; default to 0.5 in MIDI-only mode.

### Context Fields (per-step, derived)

| Field | Encoding | Range | Notes |
|---|---|---|---|
| `beat_position` | Float | 0.0–1.0 | Position within the current beat |
| `bar_position` | Float | 0.0–1.0 | Position within the current bar |
| `phrase_position` | Float | 0.0–1.0 | Estimated position within current phrase (learned, not rule-based) |

### User Embedding (conditioning)

| Field | Encoding | Dimension | Notes |
|---|---|---|---|
| `user_embedding` | Float vector | 32–64d | Per-user style vector. Conditions generation. Updated across sessions. |

## Tokenization Strategy

For the autoregressive model, events are tokenized into a flat sequence:

```
[TIME_SHIFT_t] [PITCH_p] [VELOCITY_v] [DURATION_d] [PEDAL_s] [TIMBRE_b_a_r]
```

### Vocabulary

| Token Type | Bins | Notes |
|---|---|---|
| `TIME_SHIFT` | 100 | Log-spaced from 1ms to 2s |
| `PITCH` | 128 | MIDI pitch values |
| `VELOCITY` | 32 | Quantized (4 bits) — 32 levels preserves expressiveness |
| `DURATION` | 64 | Log-spaced from 10ms to 4s |
| `PEDAL` | 4 | Off, low, medium, full |
| `BRIGHTNESS` | 16 | Timbral output bins |
| `ATTACK` | 16 | Timbral output bins |
| `RICHNESS` | 16 | Timbral output bins |
| `SPECIAL` | 4 | [PAD], [BOS], [EOS], [SEP] |

**Total vocabulary size**: ~408 tokens

This is deliberately small — keeps embedding tables compact and inference fast.

## Comparison with SongDriver

| Aspect | SongDriver | Apollo |
|---|---|---|
| Pitch | Raw MIDI pitch values in 1D array | PITCH tokens (128) |
| Timing | Fixed 16th-note grid sampling | Continuous TIME_SHIFT (log-spaced) |
| Velocity | Not modeled | 32-level VELOCITY tokens |
| Duration | Not modeled (implicit from grid) | 64-level DURATION tokens |
| Pedal | Not modeled | 4-level PEDAL tokens |
| Timbre | Not modeled | 5 continuous descriptors (brightness, attack, richness, warmth, flux) |
| Harmony | Explicit chord labels (Western theory) | Emergent from pitch patterns (no hardcoded theory) |
| Texture | Rule-based patterns | Learned generation |
| User adaptation | None | 32–64d user embedding |

## MIDI CC Output Mapping (for synth control)

When Apollo outputs events, the timbral descriptors are sent as MIDI CC:

| Descriptor | Default CC | Typical Synth Mapping |
|---|---|---|
| `brightness` | CC 74 (Filter Cutoff) | Low-pass filter frequency |
| `attack` | CC 73 (Attack Time) | Amplitude envelope attack |
| `richness` | CC 71 (Resonance) | Filter resonance / oscillator detune |
| `warmth` | CC 70 (Sound Variation) | Tone/timbre warmth — inverse brightness |
| `flux` | CC 1 (Modulation) | Vibrato / tremolo depth |

These are user-remappable in the Apollo UI.

## Open Questions

1. Should we use a compound token (all fields in one step) vs sequential tokens?
   - Compound: faster inference (1 forward pass per event), but larger output space
   - Sequential: simpler model, but multiple passes per event
   - **Leaning toward**: compound token with factored output heads

2. **Resolved:** 5 timbral descriptors implemented — brightness, attack, richness, warmth, flux.
   All derived from FFT analysis (spectral.py). Warmth and flux added beyond initial design.

3. Beat/bar position: derive from tempo detection on the input, or learn implicitly?
   - **Leaning toward**: simple onset-based beat tracker on input, explicit encoding

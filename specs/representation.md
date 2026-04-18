# Spec: `src/representation.py` — Event Representation & Tokenization

## Module purpose

Converts MIDI files into Apollo's internal event format (`ApolloEvent`) and
into/out of a flat token sequence suitable for a Transformer. Also emits a
parallel continuous side-channel of spectral features.

The token vocabulary is a single flat space of size 380, partitioned by offset
into seven regions (time_shift, pitch, velocity, duration, pedal, timbre
buckets, specials). Each musical event becomes exactly 5 tokens (or 8 if
timbre tokens are included).

## Constants (reference)

| Name | Value | Meaning |
|---|---|---|
| `VOCAB_SIZE` | 380 | Total token vocabulary |
| `TOKENS_PER_EVENT` | 5 | time_shift + pitch + velocity + duration + pedal |
| `TOKENS_PER_EVENT_WITH_TIMBRE` | 8 | adds brightness + attack + richness |
| `SPECTRAL_DIM` | 5 | brightness, attack, richness, warmth, flux |
| `TRAJECTORY_DIM` | 16 | phrase-level trajectory embedding |
| `CONTINUOUS_DIM` | 21 | SPECTRAL_DIM + TRAJECTORY_DIM |

### Token offset regions

| Region | Offset | Size | Valid token range |
|---|---|---|---|
| time_shift | 0 | 100 | [0, 99] |
| pitch | 100 | 128 | [100, 227] |
| velocity | 228 | 32 | [228, 259] |
| duration | 260 | 64 | [260, 323] |
| pedal | 324 | 4 | [324, 327] |
| brightness | 328 | 16 | [328, 343] |
| attack | 344 | 16 | [344, 359] |
| richness | 360 | 16 | [360, 375] |
| pad / bos / eos / sep | 376–379 | 4 | specials |

---

## `quantize(value, bins)` → int

- **R1.1** Returns a Python `int`.
- **R1.2** Returns a value in `[0, len(bins) - 1]` for any finite input.
- **R1.3** The returned index `i` satisfies `|bins[i] - value| == min_j |bins[j] - value|`
  (nearest-neighbour under L1 distance).
- **R1.4** Values beyond the bin range clamp to the boundary bin
  (smaller than `bins[0]` → 0, larger than `bins[-1]` → `len(bins) - 1`).

## `dequantize(index, bins)` → float

- **R2.1** Returns a Python `float`.
- **R2.2** Negative indices clamp to 0; indices ≥ `len(bins)` clamp to `len(bins) - 1`.
- **R2.3** For valid `index`, returns `bins[index]` exactly.

---

## `ApolloEvent` (dataclass)

- **R3.1** Default `brightness`, `attack`, `richness`, `warmth`, `flux` are `0.5`.
- **R3.2** Default `trajectory` is an `ndarray` of shape `(TRAJECTORY_DIM,)` (= 16)
  filled with `0.0`.
- **R3.3** Default `onset_time` is `0.0`.
- **R3.4** Each event instance has its own `trajectory` array (no shared
  mutable default).

---

## `midi_to_events(midi_path, max_events=2048, ...)` → `List[ApolloEvent]`

- **R4.1** Returns a list of `ApolloEvent`.
- **R4.2** Every event has `0 <= pitch <= 127`.
- **R4.3** Every event has `pedal` in `{0, 1, 2, 3}`.
- **R4.4** Every event has `delta_time >= 0.0` (clamped; no negative deltas
  even when instruments overlap).
- **R4.5** Cumulative onset time across returned events is monotonically
  non-decreasing (notes emitted in onset order; within same onset, by pitch).
- **R4.6** Drum instruments (`inst.is_drum`) contribute no events.
- **R4.7** When `spectral_analyzer` is `None`, all timbral fields on every
  returned event are the dataclass default `0.5`.
- **R4.8** Per-instrument note count is capped at `max_events`.
- **R4.9** `velocity` is normalized to `[0.0, 1.0]` (MIDI velocity / 127).
- **R4.10** `duration = note.end - note.start` is non-negative.

---

## `events_to_tokens(events, include_timbre_tokens=False)` → `List[int]`

- **R5.1** First element is the BOS token (`TOKEN_OFFSETS['bos']` = 377).
- **R5.2** Last element is the EOS token (`TOKEN_OFFSETS['eos']` = 378).
- **R5.3** Without timbre tokens: output length is `2 + 5 * len(events)`.
- **R5.4** With timbre tokens: output length is `2 + 8 * len(events)`.
- **R5.5** Every token value lies in `[0, VOCAB_SIZE - 1]` = `[0, 379]`.
- **R5.6** For each event, the 5 (or 8) tokens appear in a fixed order, each
  falling into its declared region:
  - positions `[0]` in `[0, 99]` (time_shift)
  - positions `[1]` in `[100, 227]` (pitch)
  - positions `[2]` in `[228, 259]` (velocity)
  - positions `[3]` in `[260, 323]` (duration)
  - positions `[4]` in `[324, 327]` (pedal)
  - (if timbre) `[5]` in `[328, 343]`, `[6]` in `[344, 359]`, `[7]` in `[360, 375]`
- **R5.7** The pitch token value equals `100 + event.pitch` (no quantization).
- **R5.8** The pedal token value equals `324 + event.pedal` (no quantization).
- **R5.9** Empty events list produces exactly `[BOS, EOS]`.

---

## `events_to_continuous(events)` → `np.ndarray`

- **R6.1** Output has shape `(len(events), CONTINUOUS_DIM)` = `(n, 21)`.
- **R6.2** Output `dtype` is `np.float32`.
- **R6.3** For each row `i`: columns 0..4 are `brightness, attack, richness,
  warmth, flux` from `events[i]`.
- **R6.4** Columns 5..20 are the first 16 values of `events[i].trajectory`.
- **R6.5** Empty input produces shape `(0, 21)`.

---

## `tokens_to_events(tokens)` → `List[ApolloEvent]`

- **R7.1** A leading BOS token is skipped.
- **R7.2** Iteration halts at the first EOS or SEP token.
- **R7.3** Every reconstructed event has `0 <= pitch <= 127`.
- **R7.4** Every reconstructed event has `pedal` in `{0, 1, 2, 3}`.
- **R7.5** Roundtrip `events → tokens → events` preserves `pitch` and `pedal`
  exactly for every event.
- **R7.6** Roundtrip `delta_time`, `velocity`, and `duration` are reconstructed
  within quantization error of their bins (not bit-exact).
- **R7.7** Malformed 5-token groups (out-of-range pitch/vel/dur/pedal) are
  silently skipped; the function never raises.

---

## `events_to_midi(events, output_path, tempo=120.0)` → `PrettyMIDI`

- **R8.1** Writes a file at `output_path` that loads successfully via
  `pretty_midi.PrettyMIDI`.
- **R8.2** The written MIDI contains exactly `len(events)` notes (one per event).
- **R8.3** Note pitches in the output equal the input events' pitches in order.
- **R8.4** Note onset times are the cumulative sum of `delta_time` across events.
- **R8.5** For events with `pedal > 0`, a CC #64 control change is emitted at
  the note's onset time.

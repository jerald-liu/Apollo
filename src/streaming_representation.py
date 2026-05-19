"""Apollo streaming token representation.

Replaces the 5-token-per-event compound format with a note-on / note-off
split that lets the model respond to a key-press before the key is released.

Vocabulary (259 tokens total vs 380 in base representation):

    time_shift : 64 bins  log-spaced 1ms–2s       → 0  … 63
    note_on    : 88 keys  MIDI 21–108  (A0–C8)    → 64 … 151
    velocity   : 16 bins  linear 1–127             → 152 … 167
    note_off   : 88 keys  MIDI 21–108              → 168 … 255
    bos        :                                    → 256
    eos        :                                    → 257
    sep        :                                    → 258   (input | output boundary)

Per-event token counts:

    note_on  → [time_shift, note_on_pitch, velocity]    = 3 tokens
    note_off → [time_shift, note_off_pitch]              = 2 tokens

The note_on triplet is emitted *immediately* when a key is pressed — the
model sees the pitch and velocity without waiting for key release.  The
note_off pair follows when the key lifts.

Average tokens per note (on+off combined): 2.5, vs 5 in the base
representation.  A 512-token window therefore covers ~200 note events
instead of ~100.

Timing: time_shift encodes the delta since the *previous token event*
(whether that was a note_on or note_off), not since the previous note_on.
This captures the full temporal texture including overlapping notes.

Key constants
-------------
MIDI_LO, MIDI_HI   : inclusive pitch range (21, 108)
N_PITCH             : 88
N_VELOCITY_BINS     : 16
N_TIME_BINS         : 64
VOCAB_SIZE          : 259
TOKENS_PER_NOTE_ON  : 3
TOKENS_PER_NOTE_OFF : 2
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# Piano pitch range
# ---------------------------------------------------------------------------

MIDI_LO   = 21   # A0
MIDI_HI   = 108  # C8
N_PITCH   = MIDI_HI - MIDI_LO + 1   # 88

# ---------------------------------------------------------------------------
# Quantisation tables
# ---------------------------------------------------------------------------

N_TIME_BINS     = 64
N_VELOCITY_BINS = 16

TIME_BINS     = np.exp(np.linspace(np.log(0.001), np.log(2.0), N_TIME_BINS))
VELOCITY_BINS = np.linspace(1, 127, N_VELOCITY_BINS)

# ---------------------------------------------------------------------------
# Token offsets
# ---------------------------------------------------------------------------

OFFSETS = {
    'time_shift': 0,                           #  0 –  63
    'note_on':    N_TIME_BINS,                 # 64 – 151
    'velocity':   N_TIME_BINS + N_PITCH,       # 152 – 167
    'note_off':   N_TIME_BINS + N_PITCH + N_VELOCITY_BINS,  # 168 – 255
    'bos':        N_TIME_BINS + N_PITCH + N_VELOCITY_BINS + N_PITCH,      # 256
    'eos':        N_TIME_BINS + N_PITCH + N_VELOCITY_BINS + N_PITCH + 1,  # 257
    'sep':        N_TIME_BINS + N_PITCH + N_VELOCITY_BINS + N_PITCH + 2,  # 258
}

VOCAB_SIZE          = N_TIME_BINS + N_PITCH + N_VELOCITY_BINS + N_PITCH + 3  # 259
TOKENS_PER_NOTE_ON  = 3
TOKENS_PER_NOTE_OFF = 2

# Typical duration used when note_off hasn't arrived yet (median from MAESTRO)
MEDIAN_DURATION_S = 0.098

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _quantize(value: float, bins: np.ndarray) -> int:
    return int(np.argmin(np.abs(bins - value)))


def _dequantize(idx: int, bins: np.ndarray) -> float:
    return float(bins[np.clip(idx, 0, len(bins) - 1)])


def pitch_to_idx(midi_pitch: int) -> int:
    """MIDI pitch 21-108 → 0-87 index. Clamps out-of-range."""
    return int(np.clip(midi_pitch - MIDI_LO, 0, N_PITCH - 1))


def idx_to_pitch(idx: int) -> int:
    return int(np.clip(idx, 0, N_PITCH - 1)) + MIDI_LO


# ---------------------------------------------------------------------------
# Event dataclass
# ---------------------------------------------------------------------------

@dataclass
class StreamNoteOn:
    pitch:      int    # MIDI 21-108
    velocity:   float  # 0.0-1.0 normalised
    delta_time: float  # seconds since previous event (on or off)


@dataclass
class StreamNoteOff:
    pitch:      int    # MIDI 21-108
    delta_time: float  # seconds since previous event


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------

def encode_note_on(event: StreamNoteOn) -> List[int]:
    """Encode a note-on event as 3 tokens: [time_shift, note_on_pitch, velocity]."""
    ts  = _quantize(event.delta_time, TIME_BINS) + OFFSETS['time_shift']
    pit = pitch_to_idx(event.pitch)              + OFFSETS['note_on']
    vel = _quantize(event.velocity * 127, VELOCITY_BINS) + OFFSETS['velocity']
    return [ts, pit, vel]


def encode_note_off(event: StreamNoteOff) -> List[int]:
    """Encode a note-off event as 2 tokens: [time_shift, note_off_pitch]."""
    ts  = _quantize(event.delta_time, TIME_BINS) + OFFSETS['time_shift']
    pit = pitch_to_idx(event.pitch)              + OFFSETS['note_off']
    return [ts, pit]


def midi_to_streaming_tokens(midi_path: str, max_events: int = 2048) -> List[int]:
    """Convert a MIDI file to a streaming token sequence (note-on/note-off interleaved).

    Events are ordered by absolute time.  note_on and note_off for the same
    note may be separated by many other tokens (as in real performance).
    """
    import pretty_midi
    pm = pretty_midi.PrettyMIDI(str(midi_path))

    # Collect all note-on and note-off events with absolute timestamps
    raw: List[Tuple[float, str, int, float]] = []  # (time, kind, pitch, velocity)
    for inst in pm.instruments:
        if inst.is_drum:
            continue
        for note in inst.notes[:max_events]:
            raw.append((note.start, 'on',  note.pitch, note.velocity / 127.0))
            raw.append((note.end,   'off', note.pitch, 0.0))

    raw.sort(key=lambda x: (x[0], x[1] == 'on'))  # tie-break: offs before ons

    tokens = [OFFSETS['bos']]
    prev_time = 0.0

    for abs_time, kind, pitch, velocity in raw:
        delta = max(abs_time - prev_time, 0.0)
        prev_time = abs_time

        if kind == 'on':
            ev = StreamNoteOn(pitch=pitch, velocity=velocity, delta_time=delta)
            tokens.extend(encode_note_on(ev))
        else:
            ev = StreamNoteOff(pitch=pitch, delta_time=delta)
            tokens.extend(encode_note_off(ev))

    tokens.append(OFFSETS['eos'])
    return tokens


# ---------------------------------------------------------------------------
# Decoding
# ---------------------------------------------------------------------------

def streaming_tokens_to_events(tokens: List[int]) -> List[dict]:
    """Decode a streaming token sequence back to a list of note dicts.

    Returns list of {'pitch', 'velocity', 'onset', 'offset'} with onset/offset
    in seconds relative to start.  Dangling note-ons (no matching note-off)
    get offset = onset + MEDIAN_DURATION_S.
    """
    i = 0
    if tokens and tokens[0] == OFFSETS['bos']:
        i = 1

    current_time = 0.0
    pending: dict[int, dict] = {}   # pitch → {pitch, velocity, onset}
    notes: List[dict] = []

    while i < len(tokens):
        t = tokens[i]
        if t in (OFFSETS['eos'], OFFSETS['sep']):
            break

        # time_shift
        if OFFSETS['time_shift'] <= t < OFFSETS['note_on']:
            delta = _dequantize(t - OFFSETS['time_shift'], TIME_BINS)
            current_time += delta
            i += 1
            continue

        # note_on: [note_on_pitch, velocity] follow immediately
        if OFFSETS['note_on'] <= t < OFFSETS['velocity']:
            pitch = idx_to_pitch(t - OFFSETS['note_on'])
            if i + 1 < len(tokens):
                vel_tok = tokens[i + 1]
                if OFFSETS['velocity'] <= vel_tok < OFFSETS['note_off']:
                    vel = _dequantize(vel_tok - OFFSETS['velocity'], VELOCITY_BINS) / 127.0
                    pending[pitch] = {'pitch': pitch, 'velocity': vel, 'onset': current_time}
                    i += 2
                    continue
            i += 1
            continue

        # note_off: [note_off_pitch]
        if OFFSETS['note_off'] <= t < OFFSETS['bos']:
            pitch = idx_to_pitch(t - OFFSETS['note_off'])
            if pitch in pending:
                entry = pending.pop(pitch)
                entry['offset'] = current_time
                notes.append(entry)
            i += 1
            continue

        i += 1

    # Close any still-open notes
    for pitch, entry in pending.items():
        entry['offset'] = entry['onset'] + MEDIAN_DURATION_S
        notes.append(entry)

    return sorted(notes, key=lambda n: n['onset'])


def streaming_notes_to_midi(notes: List[dict], output_path: str, tempo: float = 120.0):
    """Write decoded notes to a MIDI file."""
    import pretty_midi
    pm   = pretty_midi.PrettyMIDI(initial_tempo=tempo)
    inst = pretty_midi.Instrument(program=0, name='Apollo-stream')
    for n in notes:
        inst.notes.append(pretty_midi.Note(
            velocity=int(np.clip(n['velocity'] * 127, 1, 127)),
            pitch=int(n['pitch']),
            start=float(n['onset']),
            end=float(n['offset']),
        ))
    pm.instruments.append(inst)
    pm.write(str(output_path))
    return pm

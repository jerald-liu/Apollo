"""Apollo event representation and tokenization.

Converts MIDI data to/from Apollo's internal event format.
Supports both token-only mode and hybrid token+continuous mode
for spectral features.
"""

import numpy as np
import pretty_midi
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# --- Quantization bins ---

# Time shift: 100 bins, log-spaced from 1ms to 2s
TIME_SHIFT_BINS = np.exp(np.linspace(np.log(0.001), np.log(2.0), 100))

# Duration: 64 bins, log-spaced from 10ms to 4s
DURATION_BINS = np.exp(np.linspace(np.log(0.01), np.log(4.0), 64))

# Velocity: 32 linear bins
VELOCITY_BINS = np.linspace(1, 127, 32)

# --- Token offsets ---
# We pack all token types into a single vocabulary with offsets

TOKEN_OFFSETS = {
    'time_shift': 0,      # 0-99
    'pitch': 100,          # 100-227
    'velocity': 228,       # 228-259
    'duration': 260,       # 260-323
    'pedal': 324,          # 324-327
    'brightness': 328,     # 328-343
    'attack': 344,         # 344-359
    'richness': 360,       # 360-375
    'pad': 376,
    'bos': 377,
    'eos': 378,
    'sep': 379,            # separator between input melody and generated response
}

VOCAB_SIZE = 380

# Number of continuous spectral features per event
# [brightness, attack, richness, warmth, flux] + trajectory embedding (16d)
SPECTRAL_DIM = 5
TRAJECTORY_DIM = 16
CONTINUOUS_DIM = SPECTRAL_DIM + TRAJECTORY_DIM  # 21 total

# --- Helper functions ---


def quantize(value: float, bins: np.ndarray) -> int:
    """Quantize a continuous value to the nearest bin index."""
    return int(np.argmin(np.abs(bins - value)))


def dequantize(index: int, bins: np.ndarray) -> float:
    """Convert a bin index back to a continuous value."""
    return float(bins[np.clip(index, 0, len(bins) - 1)])


@dataclass
class ApolloEvent:
    """A single musical event in Apollo's representation."""
    pitch: int              # 0-127 MIDI pitch
    velocity: float         # 0.0-1.0 normalized
    delta_time: float       # seconds since previous event
    duration: float         # note duration in seconds
    pedal: int              # 0-3 (off, low, medium, full)
    # Timbral descriptors (normalized 0-1, from spectral analysis)
    brightness: float = 0.5  # spectral centroid
    attack: float = 0.5      # onset strength
    richness: float = 0.5    # spectral flatness
    warmth: float = 0.5      # inverse rolloff
    flux: float = 0.5        # spectral flux (rate of change)
    # Spectral trajectory context (phrase-level timbral arc)
    trajectory: np.ndarray = field(default_factory=lambda: np.full(TRAJECTORY_DIM, 0.0))
    # Absolute onset time (for spectral alignment — not tokenized)
    onset_time: float = 0.0


def midi_to_events(
    midi_path: str,
    max_events: int = 2048,
    spectral_analyzer=None,
    audio_path: str = None,
    spectral_norm_stats: dict = None,
) -> List[ApolloEvent]:
    """Convert a MIDI file to a list of ApolloEvents.

    Args:
        midi_path: Path to MIDI file
        max_events: Maximum events to extract
        spectral_analyzer: Optional SpectralAnalyzer instance for timbral extraction
        audio_path: Path to paired audio (required if spectral_analyzer is provided)
        spectral_norm_stats: Normalization stats dict for spectral features
    """
    pm = pretty_midi.PrettyMIDI(str(midi_path))
    events = []

    # Optionally analyze audio for spectral features
    spectral_arrays = None
    trajectory = None
    if spectral_analyzer is not None and audio_path is not None:
        from spectral import SpectralTrajectory
        spectral_arrays = spectral_analyzer.analyze_audio_to_arrays(str(audio_path))
        trajectory = SpectralTrajectory(spectral_arrays, window_sec=2.0, hop_sec=0.5)

    for inst in pm.instruments:
        if inst.is_drum:
            continue

        # Build pedal state timeline
        pedal_times = []
        pedal_values = []
        for cc in inst.control_changes:
            if cc.number == 64:  # sustain pedal
                pedal_times.append(cc.time)
                pedal_values.append(cc.value)

        # Sort notes by onset
        notes = sorted(inst.notes, key=lambda n: (n.start, n.pitch))

        prev_onset = 0.0
        for note in notes[:max_events]:
            delta = note.start - prev_onset

            # Find pedal state at note onset
            pedal_state = 0
            if pedal_times:
                idx = np.searchsorted(pedal_times, note.start, side='right') - 1
                if idx >= 0:
                    val = pedal_values[idx]
                    if val >= 96:
                        pedal_state = 3
                    elif val >= 64:
                        pedal_state = 2
                    elif val >= 32:
                        pedal_state = 1
                    else:
                        pedal_state = 0

            # Extract spectral features if available
            brightness = 0.5
            attack_val = 0.5
            richness = 0.5
            warmth = 0.5
            flux = 0.5
            traj_emb = np.zeros(TRAJECTORY_DIM)

            if spectral_arrays is not None:
                profile = spectral_analyzer.get_note_profile(
                    spectral_arrays, note.start, note.end
                )
                if spectral_norm_stats is not None:
                    profile = spectral_analyzer.normalize_profile(profile, spectral_norm_stats)
                brightness = profile.brightness
                attack_val = profile.attack
                richness = profile.richness
                warmth = profile.warmth
                flux = profile.flux

            if trajectory is not None:
                traj_emb = trajectory.to_embedding(note.start, dim=TRAJECTORY_DIM)

            events.append(ApolloEvent(
                pitch=note.pitch,
                velocity=note.velocity / 127.0,
                delta_time=max(delta, 0.0),
                duration=note.end - note.start,
                pedal=pedal_state,
                brightness=brightness,
                attack=attack_val,
                richness=richness,
                warmth=warmth,
                flux=flux,
                trajectory=traj_emb,
                onset_time=note.start,
            ))
            prev_onset = note.start

    return events


def events_to_tokens(events: List[ApolloEvent], include_timbre_tokens: bool = False) -> List[int]:
    """Convert ApolloEvents to a token sequence.

    Args:
        events: List of ApolloEvents
        include_timbre_tokens: If True, include quantized brightness/attack/richness tokens.
            These are the tokenized (discretized) version of timbral descriptors.
            The continuous versions are available via events_to_continuous().
    """
    tokens = [TOKEN_OFFSETS['bos']]

    for e in events:
        # Time shift
        ts_bin = quantize(e.delta_time, TIME_SHIFT_BINS)
        tokens.append(TOKEN_OFFSETS['time_shift'] + ts_bin)

        # Pitch
        tokens.append(TOKEN_OFFSETS['pitch'] + e.pitch)

        # Velocity
        vel_bin = quantize(e.velocity * 127, VELOCITY_BINS)
        tokens.append(TOKEN_OFFSETS['velocity'] + vel_bin)

        # Duration
        dur_bin = quantize(e.duration, DURATION_BINS)
        tokens.append(TOKEN_OFFSETS['duration'] + dur_bin)

        # Pedal
        tokens.append(TOKEN_OFFSETS['pedal'] + e.pedal)

        # Optional: quantized timbral tokens
        if include_timbre_tokens:
            tokens.append(TOKEN_OFFSETS['brightness'] + int(np.clip(e.brightness * 15, 0, 15)))
            tokens.append(TOKEN_OFFSETS['attack'] + int(np.clip(e.attack * 15, 0, 15)))
            tokens.append(TOKEN_OFFSETS['richness'] + int(np.clip(e.richness * 15, 0, 15)))

    tokens.append(TOKEN_OFFSETS['eos'])
    return tokens


# Number of tokens per event (without timbre tokens)
TOKENS_PER_EVENT = 5
# Number of tokens per event (with timbre tokens)
TOKENS_PER_EVENT_WITH_TIMBRE = 8


def events_to_continuous(events: List[ApolloEvent]) -> np.ndarray:
    """Extract continuous spectral features aligned to events.

    Returns array of shape (n_events, CONTINUOUS_DIM) where each row is:
        [brightness, attack, richness, warmth, flux, trajectory_0, ..., trajectory_15]

    These are passed as side-channel input to the model alongside tokens.
    """
    n = len(events)
    features = np.zeros((n, CONTINUOUS_DIM), dtype=np.float32)

    for i, e in enumerate(events):
        features[i, 0] = e.brightness
        features[i, 1] = e.attack
        features[i, 2] = e.richness
        features[i, 3] = e.warmth
        features[i, 4] = e.flux
        features[i, 5:5 + TRAJECTORY_DIM] = e.trajectory[:TRAJECTORY_DIM]

    return features


def tokens_to_events(tokens: List[int]) -> List[ApolloEvent]:
    """Convert a token sequence back to ApolloEvents."""
    events = []
    i = 0

    # Skip BOS
    if tokens and tokens[0] == TOKEN_OFFSETS['bos']:
        i = 1

    while i < len(tokens):
        tok = tokens[i]

        # Stop at EOS or SEP
        if tok == TOKEN_OFFSETS['eos'] or tok == TOKEN_OFFSETS['sep']:
            break

        # Expect: time_shift, pitch, velocity, duration, pedal
        if tok < TOKEN_OFFSETS['pitch']:  # time_shift token
            ts_bin = tok - TOKEN_OFFSETS['time_shift']
            delta_time = dequantize(ts_bin, TIME_SHIFT_BINS)

            if i + 4 >= len(tokens):
                break

            pitch = tokens[i + 1] - TOKEN_OFFSETS['pitch']
            vel_bin = tokens[i + 2] - TOKEN_OFFSETS['velocity']
            dur_bin = tokens[i + 3] - TOKEN_OFFSETS['duration']
            pedal = tokens[i + 4] - TOKEN_OFFSETS['pedal']

            # Validate ranges
            if 0 <= pitch <= 127 and 0 <= vel_bin < 32 and 0 <= dur_bin < 64 and 0 <= pedal <= 3:
                events.append(ApolloEvent(
                    pitch=pitch,
                    velocity=dequantize(vel_bin, VELOCITY_BINS) / 127.0,
                    delta_time=delta_time,
                    duration=dequantize(dur_bin, DURATION_BINS),
                    pedal=pedal,
                ))
            i += 5
        else:
            i += 1  # skip unexpected tokens

    return events


def events_to_midi(events: List[ApolloEvent], output_path: str, tempo: float = 120.0):
    """Convert ApolloEvents to a MIDI file."""
    pm = pretty_midi.PrettyMIDI(initial_tempo=tempo)
    inst = pretty_midi.Instrument(program=0, name='Apollo')

    current_time = 0.0
    for e in events:
        current_time += e.delta_time
        note = pretty_midi.Note(
            velocity=int(np.clip(e.velocity * 127, 1, 127)),
            pitch=int(np.clip(e.pitch, 0, 127)),
            start=current_time,
            end=current_time + e.duration,
        )
        inst.notes.append(note)

        # Add pedal CC
        if e.pedal > 0:
            pedal_val = [0, 40, 80, 120][e.pedal]
            inst.control_changes.append(
                pretty_midi.ControlChange(number=64, value=pedal_val, time=current_time)
            )

    pm.instruments.append(inst)
    pm.write(str(output_path))
    return pm

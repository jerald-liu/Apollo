"""Shared fixtures for Apollo tests.

All fixtures produce synthetic data so tests can run in CI without the
MAESTRO dataset or any network access.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

# Make `src` and `scripts` importable without installing the project.
ROOT = Path(__file__).parent.parent
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
for p in (SRC, SCRIPTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


# --- Synthetic MIDI --------------------------------------------------------

@pytest.fixture
def synthetic_midi_path(tmp_path):
    """Write a small deterministic MIDI file and return its path.

    20 notes, ascending C major scale with a sustain pedal press in the middle.
    Enough events to exceed the 10-note floor in process_file.
    """
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(initial_tempo=120.0)
    inst = pretty_midi.Instrument(program=0, name="test")

    pitches = [60, 62, 64, 65, 67, 69, 71, 72, 74, 76,
               77, 79, 81, 83, 84, 86, 88, 89, 91, 93]
    for i, pitch in enumerate(pitches):
        start = i * 0.25
        end = start + 0.2
        inst.notes.append(pretty_midi.Note(
            velocity=80, pitch=pitch, start=start, end=end
        ))

    # Pedal press during the middle of the sequence
    inst.control_changes.append(
        pretty_midi.ControlChange(number=64, value=100, time=1.0)
    )
    inst.control_changes.append(
        pretty_midi.ControlChange(number=64, value=0, time=3.0)
    )

    pm.instruments.append(inst)

    path = tmp_path / "synthetic.mid"
    pm.write(str(path))
    return path


@pytest.fixture
def corrupt_midi_path(tmp_path):
    """A file with .mid extension that is NOT valid MIDI."""
    path = tmp_path / "corrupt.mid"
    path.write_bytes(b"this is not a midi file")
    return path


# --- Synthetic audio -------------------------------------------------------

@pytest.fixture
def synthetic_audio_arrays():
    """Hand-built spectral-arrays dict that mimics SpectralAnalyzer output.

    Useful for testing get_note_profile, compute_normalization_stats,
    SpectralTrajectory without running librosa.
    """
    n_frames = 200
    # ~23ms/frame for sr=22050, hop=512
    times = np.arange(n_frames) * (512 / 22050)
    rng = np.random.default_rng(42)
    return {
        "times": times,
        "centroid": rng.uniform(500, 5000, n_frames).astype(np.float32),
        "flux": np.concatenate([[0.0], rng.uniform(0, 1, n_frames - 1)]).astype(np.float32),
        "rolloff": rng.uniform(1000, 8000, n_frames).astype(np.float32),
        "flatness": rng.uniform(0, 1, n_frames).astype(np.float32),
        "bandwidth": rng.uniform(500, 3000, n_frames).astype(np.float32),
        "rms": rng.uniform(0, 1, n_frames).astype(np.float32),
        "onset_strength": rng.uniform(0, 5, n_frames).astype(np.float32),
    }


@pytest.fixture
def synthetic_audio_file(tmp_path):
    """Write a short sine-wave WAV so librosa has something real to analyze."""
    import soundfile as sf

    sr = 22050
    dur = 1.0
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    # Two-tone signal so spectral flux is non-trivial
    y = 0.4 * np.sin(2 * np.pi * 440 * t) + 0.2 * np.sin(2 * np.pi * 880 * t)
    path = tmp_path / "tone.wav"
    sf.write(str(path), y, sr)
    return path

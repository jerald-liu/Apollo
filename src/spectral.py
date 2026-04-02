"""Apollo spectral analysis — FFT-over-time feature extraction.

Extracts frame-level and note-level spectral features from audio,
aligned to MIDI events. These features become the timbral descriptors
that Apollo learns to predict.

Spectral features extracted:
- spectral_centroid: brightness (Hz) — maps to filter cutoff
- spectral_flux: rate of spectral change — captures transitions
- spectral_rolloff: frequency below which 85% of energy lies
- spectral_flatness: tonality vs noise (0=tonal, 1=noisy)
- spectral_bandwidth: spread of spectrum around centroid
- rms_energy: loudness envelope
- onset_strength: attack sharpness at each frame
"""

import numpy as np
import librosa
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from pathlib import Path


@dataclass
class SpectralFrame:
    """Spectral features for a single time frame."""
    time: float                  # seconds
    centroid: float              # Hz — brightness
    flux: float                  # spectral change rate
    rolloff: float               # Hz — energy concentration
    flatness: float              # 0-1 — tonality
    bandwidth: float             # Hz — spectral spread
    rms: float                   # loudness
    onset_strength: float        # attack strength


@dataclass
class NoteSpectralProfile:
    """Spectral features aggregated over a note's duration."""
    # Means over the note window
    brightness: float            # normalized centroid (0-1)
    attack: float                # normalized onset strength (0-1)
    richness: float              # normalized flatness (0-1)
    warmth: float                # inverse rolloff — low rolloff = warm (0-1)
    flux: float                  # spectral change during note (0-1)
    dynamic_envelope: np.ndarray = field(default_factory=lambda: np.array([]))  # RMS over time within note


class SpectralAnalyzer:
    """Extracts spectral features from audio, aligned to MIDI events."""

    def __init__(
        self,
        sr: int = 22050,
        n_fft: int = 2048,
        hop_length: int = 512,
        n_mels: int = 128,
    ):
        self.sr = sr
        self.n_fft = n_fft
        self.hop_length = hop_length
        self.n_mels = n_mels
        self.frame_duration = hop_length / sr  # ~23ms per frame at defaults

    def analyze_audio(self, audio_path: str) -> List[SpectralFrame]:
        """Extract frame-level spectral features from an audio file."""
        y, _ = librosa.load(audio_path, sr=self.sr)

        # Compute spectral features
        S = np.abs(librosa.stft(y, n_fft=self.n_fft, hop_length=self.hop_length))

        centroid = librosa.feature.spectral_centroid(
            S=S, sr=self.sr
        )[0]
        rolloff = librosa.feature.spectral_rolloff(
            S=S, sr=self.sr, roll_percent=0.85
        )[0]
        flatness = librosa.feature.spectral_flatness(
            S=S
        )[0]
        bandwidth = librosa.feature.spectral_bandwidth(
            S=S, sr=self.sr
        )[0]
        rms = librosa.feature.rms(
            S=S
        )[0]
        onset_env = librosa.onset.onset_strength(
            y=y, sr=self.sr, hop_length=self.hop_length
        )

        # Spectral flux (frame-to-frame difference in spectrum)
        flux = np.zeros(S.shape[1])
        flux[1:] = np.sqrt(np.sum(np.diff(S, axis=1) ** 2, axis=0))

        # Build frame list
        n_frames = min(len(centroid), len(rolloff), len(flatness),
                       len(bandwidth), len(rms), len(onset_env), len(flux))
        frames = []
        for i in range(n_frames):
            t = librosa.frames_to_time(i, sr=self.sr, hop_length=self.hop_length)
            frames.append(SpectralFrame(
                time=t,
                centroid=centroid[i],
                flux=flux[i],
                rolloff=rolloff[i],
                flatness=flatness[i],
                bandwidth=bandwidth[i],
                rms=rms[i],
                onset_strength=onset_env[i],
            ))

        return frames

    def analyze_audio_to_arrays(self, audio_path: str) -> dict:
        """Extract spectral features as numpy arrays (more efficient for batch processing)."""
        y, _ = librosa.load(audio_path, sr=self.sr)

        S = np.abs(librosa.stft(y, n_fft=self.n_fft, hop_length=self.hop_length))

        centroid = librosa.feature.spectral_centroid(S=S, sr=self.sr)[0]
        rolloff = librosa.feature.spectral_rolloff(S=S, sr=self.sr, roll_percent=0.85)[0]
        flatness = librosa.feature.spectral_flatness(S=S)[0]
        bandwidth = librosa.feature.spectral_bandwidth(S=S, sr=self.sr)[0]
        rms = librosa.feature.rms(S=S)[0]
        onset_env = librosa.onset.onset_strength(y=y, sr=self.sr, hop_length=self.hop_length)

        flux = np.zeros(S.shape[1])
        flux[1:] = np.sqrt(np.sum(np.diff(S, axis=1) ** 2, axis=0))

        n_frames = min(len(centroid), len(rolloff), len(flatness),
                       len(bandwidth), len(rms), len(onset_env), len(flux))

        times = librosa.frames_to_time(
            np.arange(n_frames), sr=self.sr, hop_length=self.hop_length
        )

        return {
            'times': times[:n_frames],
            'centroid': centroid[:n_frames],
            'flux': flux[:n_frames],
            'rolloff': rolloff[:n_frames],
            'flatness': flatness[:n_frames],
            'bandwidth': bandwidth[:n_frames],
            'rms': rms[:n_frames],
            'onset_strength': onset_env[:n_frames],
        }

    def get_note_profile(
        self,
        spectral_arrays: dict,
        note_onset: float,
        note_offset: float,
    ) -> NoteSpectralProfile:
        """Extract aggregated spectral profile for a single note's time window."""
        times = spectral_arrays['times']

        # Find frames within the note window
        # Extend slightly before onset to capture attack transient
        attack_window = 0.02  # 20ms before onset
        start_time = max(0, note_onset - attack_window)
        mask = (times >= start_time) & (times <= note_offset)

        if mask.sum() == 0:
            # Note too short or outside audio range — return defaults
            return NoteSpectralProfile(
                brightness=0.5, attack=0.5, richness=0.5,
                warmth=0.5, flux=0.5, dynamic_envelope=np.array([0.5])
            )

        centroid_slice = spectral_arrays['centroid'][mask]
        onset_slice = spectral_arrays['onset_strength'][mask]
        flatness_slice = spectral_arrays['flatness'][mask]
        rolloff_slice = spectral_arrays['rolloff'][mask]
        flux_slice = spectral_arrays['flux'][mask]
        rms_slice = spectral_arrays['rms'][mask]

        return NoteSpectralProfile(
            brightness=float(np.mean(centroid_slice)),     # raw Hz — normalize later
            attack=float(np.max(onset_slice)),             # peak onset strength
            richness=float(np.mean(flatness_slice)),       # raw — normalize later
            warmth=float(np.mean(rolloff_slice)),          # raw Hz — normalize later
            flux=float(np.mean(flux_slice)),               # raw — normalize later
            dynamic_envelope=rms_slice.copy(),
        )

    def compute_normalization_stats(
        self, profiles: List[NoteSpectralProfile]
    ) -> dict:
        """Compute min/max stats across all note profiles for normalization."""
        stats = {}
        for field_name in ['brightness', 'attack', 'richness', 'warmth', 'flux']:
            values = [getattr(p, field_name) for p in profiles]
            stats[field_name] = {
                'min': float(np.percentile(values, 2)),   # 2nd percentile (robust)
                'max': float(np.percentile(values, 98)),   # 98th percentile
                'mean': float(np.mean(values)),
                'std': float(np.std(values)),
            }
        return stats

    def normalize_profile(
        self,
        profile: NoteSpectralProfile,
        stats: dict
    ) -> NoteSpectralProfile:
        """Normalize a profile's features to 0-1 range using precomputed stats."""
        def norm(val, field_name):
            s = stats[field_name]
            if s['max'] - s['min'] < 1e-8:
                return 0.5
            return float(np.clip((val - s['min']) / (s['max'] - s['min']), 0, 1))

        return NoteSpectralProfile(
            brightness=norm(profile.brightness, 'brightness'),
            attack=norm(profile.attack, 'attack'),
            richness=norm(profile.richness, 'richness'),
            warmth=1.0 - norm(profile.warmth, 'warmth'),  # invert: low rolloff = warm
            flux=norm(profile.flux, 'flux'),
            dynamic_envelope=profile.dynamic_envelope,
        )


class SpectralTrajectory:
    """Represents spectral evolution over a musical phrase.

    This captures the higher-level "shape" of how timbre changes over time,
    beyond individual note profiles. Useful for:
    - Learning phrase-level timbral arcs (build → climax → release)
    - Detecting musical sections and transitions
    - Conditioning generation on timbral context
    """

    def __init__(self, spectral_arrays: dict, window_sec: float = 2.0, hop_sec: float = 0.5):
        """Compute smoothed spectral trajectories over overlapping windows.

        Args:
            spectral_arrays: Output from SpectralAnalyzer.analyze_audio_to_arrays()
            window_sec: Window size for trajectory smoothing (seconds)
            hop_sec: Hop between trajectory points (seconds)
        """
        times = spectral_arrays['times']
        if len(times) == 0:
            self.trajectory_times = np.array([])
            self.trajectories = {}
            return

        duration = times[-1]
        frame_dur = times[1] - times[0] if len(times) > 1 else 0.023

        window_frames = max(1, int(window_sec / frame_dur))
        hop_frames = max(1, int(hop_sec / frame_dur))

        features = ['centroid', 'flux', 'rolloff', 'flatness', 'bandwidth', 'rms']
        self.trajectories = {f: [] for f in features}
        self.trajectory_times = []

        for start in range(0, len(times) - window_frames, hop_frames):
            end = start + window_frames
            self.trajectory_times.append(times[start + window_frames // 2])
            for feat in features:
                arr = spectral_arrays[feat][start:end]
                self.trajectories[feat].append({
                    'mean': float(np.mean(arr)),
                    'std': float(np.std(arr)),
                    'delta': float(arr[-1] - arr[0]) if len(arr) > 1 else 0.0,  # trend
                })

        self.trajectory_times = np.array(self.trajectory_times)

    def get_context_at(self, time: float) -> dict:
        """Get the spectral context (trajectory state) at a given time."""
        if len(self.trajectory_times) == 0:
            return {f: {'mean': 0.5, 'std': 0.0, 'delta': 0.0}
                    for f in ['centroid', 'flux', 'rolloff', 'flatness', 'bandwidth', 'rms']}

        idx = np.searchsorted(self.trajectory_times, time, side='right') - 1
        idx = np.clip(idx, 0, len(self.trajectory_times) - 1)
        return {feat: self.trajectories[feat][idx] for feat in self.trajectories}

    def to_embedding(self, time: float, dim: int = 16) -> np.ndarray:
        """Convert trajectory context at a time point into a fixed-size vector.

        This can be concatenated with note-level features as additional
        conditioning for the model.
        """
        ctx = self.get_context_at(time)
        # Pack: [mean, std, delta] for each feature
        values = []
        for feat in ['centroid', 'flux', 'rolloff', 'flatness', 'bandwidth', 'rms']:
            values.extend([ctx[feat]['mean'], ctx[feat]['std'], ctx[feat]['delta']])

        vec = np.array(values, dtype=np.float32)  # 18 values
        # Pad or truncate to desired dimension
        if len(vec) >= dim:
            return vec[:dim]
        else:
            return np.pad(vec, (0, dim - len(vec)))

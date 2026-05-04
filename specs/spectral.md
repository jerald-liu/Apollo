# Spec: `src/spectral.py` — Spectral Analysis

## Module purpose

Extracts frame-level and note-level spectral features from audio using
librosa, aligned to MIDI onsets. These features are the timbral descriptors
that Apollo learns to predict. Also provides a phrase-level "trajectory"
abstraction that captures how timbre evolves over multi-second windows.

## Units & conventions

- All times are in **seconds** (float).
- Frequencies are in **Hz** (float).
- Normalized outputs live in `[0.0, 1.0]`.
- Default analysis: `sr=22050`, `n_fft=2048`, `hop_length=512`,
  so frame duration ≈ 23.2 ms.

---

## `SpectralFrame` (dataclass)

- **S0.1** Holds one frame's features: `time, centroid, flux, rolloff,
  flatness, bandwidth, rms, onset_strength`. All are plain `float`.

## `NoteSpectralProfile` (dataclass)

- **S0.2** Holds a note-window aggregate: `brightness, attack, richness,
  warmth, flux` (floats) plus `dynamic_envelope` (an `np.ndarray`).
- **S0.3** `dynamic_envelope` defaults to an empty array of shape `(0,)`.

---

## `SpectralAnalyzer.__init__`

- **S1.1** Stores `sr, n_fft, hop_length, n_mels` as attributes.
- **S1.2** Computes `frame_duration = hop_length / sr`.

## `SpectralAnalyzer.analyze_audio(audio_path)` → `List[SpectralFrame]`

- **S2.1** Returns a non-empty list for any non-silent input.
- **S2.2** Frame `time` values are strictly non-decreasing.
- **S2.3** Frame `time[0]` is `0.0` (first frame centred at t=0 by librosa
  defaults).
- **S2.4** Every numeric field on every frame is finite (no NaN, no inf).

## `SpectralAnalyzer.analyze_audio_to_arrays(audio_path)` → `dict`

- **S3.1** Returns a dict containing all of:
  `times, centroid, flux, rolloff, flatness, bandwidth, rms, onset_strength`.
- **S3.2** All eight arrays have identical length `N >= 1`.
- **S3.3** `times` is strictly non-decreasing.
- **S3.4** All arrays contain only finite values.
- **S3.5** `flux[0] == 0` (no previous frame to diff against).

## `SpectralAnalyzer.get_note_profile(spectral_arrays, onset, offset)` → `NoteSpectralProfile`

- **S4.1** When no frames fall in `[onset - 0.02, offset]`, returns a default
  profile with every scalar field equal to `0.5` and
  `dynamic_envelope == np.array([0.5])`.
- **S4.2** `attack` is the **maximum** of `onset_strength` within the window
  (peak onset, not mean).
- **S4.3** `brightness, richness, warmth, flux` are **means** of their
  respective arrays within the window.
- **S4.4** `dynamic_envelope` is the RMS slice within the window (copied;
  mutating the return does not alter the source arrays).
- **S4.5** The window includes a 20 ms look-back before `onset` to capture the
  attack transient.

## `SpectralAnalyzer.compute_normalization_stats(profiles)` → `dict`

- **S5.1** Returns a dict with exactly these keys:
  `brightness, attack, richness, warmth, flux`.
- **S5.2** Each sub-dict contains `min, max, mean, std` (all `float`).
- **S5.3** `min` is the 2nd percentile across profiles, `max` is the 98th
  percentile (robust to outliers).

## `SpectralAnalyzer.normalize_profile(profile, stats)` → `NoteSpectralProfile`

- **S6.1** All scalar outputs lie in `[0.0, 1.0]`.
- **S6.2** `warmth` is **inverted** relative to rolloff: a high raw rolloff
  (bright) produces a low warmth value.
- **S6.3** When `stats[field]['max'] - stats[field]['min'] < 1e-8`, the
  normalized field is `0.5` (degenerate range).
- **S6.4** `dynamic_envelope` is passed through unchanged (not normalized).

---

## `SpectralTrajectory.__init__(spectral_arrays, window_sec=2.0, hop_sec=0.5)`

- **S7.1** An empty `spectral_arrays['times']` produces a valid object with
  `trajectory_times == np.array([])` and `trajectories == {}`. Does not raise.
- **S7.2** For non-empty input, `trajectories` has keys
  `centroid, flux, rolloff, flatness, bandwidth, rms`.
- **S7.3** Each `trajectories[feat]` entry is a list of dicts with
  `mean, std, delta` (all `float`).
- **S7.4** `trajectory_times` is an `np.ndarray` strictly non-decreasing in time.

## `SpectralTrajectory.get_context_at(time)` → `dict`

- **S8.1** Returns a dict keyed by the six feature names, each with
  `mean, std, delta`.
- **S8.2** Empty trajectory returns all zeros except `mean = 0.5`.
- **S8.3** For `time` outside `[trajectory_times[0], trajectory_times[-1]]`,
  clamps to the nearest endpoint (never raises `IndexError`).

## `SpectralTrajectory.to_embedding(time, dim=16)` → `np.ndarray`

- **S9.1** Output has shape `(dim,)` for any requested `dim >= 1`.
- **S9.2** Output dtype is `np.float32`.
- **S9.3** Every value in the output is finite.
- **S9.4** `dim` larger than the natural feature-pack length (18) is padded
  with zeros; `dim` smaller truncates.
- **S9.5** Works on empty trajectory (returns finite values, usually zeros).

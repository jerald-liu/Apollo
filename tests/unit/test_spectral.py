"""Tests for src/spectral.py.

Each test cites the clause ID from specs/spectral.md that it enforces.
Tests that need real audio use a synthetic WAV fixture (two sine tones).
"""
from __future__ import annotations

import numpy as np
import pytest

from spectral import (
    NoteSpectralProfile,
    SpectralAnalyzer,
    SpectralFrame,
    SpectralTrajectory,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def analyzer():
    return SpectralAnalyzer(sr=22050, n_fft=2048, hop_length=512)


# --- dataclass defaults ----------------------------------------------------

class TestDataclasses:
    def test_S0_3_note_profile_default_envelope_empty(self):
        p = NoteSpectralProfile(brightness=0.5, attack=0.5, richness=0.5,
                                warmth=0.5, flux=0.5)
        assert isinstance(p.dynamic_envelope, np.ndarray)
        assert p.dynamic_envelope.shape == (0,)


# --- SpectralAnalyzer init -------------------------------------------------

class TestAnalyzerInit:
    def test_S1_1_stores_attrs(self):
        a = SpectralAnalyzer(sr=44100, n_fft=1024, hop_length=256, n_mels=64)
        assert a.sr == 44100
        assert a.n_fft == 1024
        assert a.hop_length == 256
        assert a.n_mels == 64

    def test_S1_2_frame_duration(self):
        a = SpectralAnalyzer(sr=22050, n_fft=2048, hop_length=512)
        assert a.frame_duration == pytest.approx(512 / 22050)


# --- analyze_audio ---------------------------------------------------------

class TestAnalyzeAudio:
    def test_S2_1_non_empty(self, analyzer, synthetic_audio_file):
        frames = analyzer.analyze_audio(str(synthetic_audio_file))
        assert len(frames) > 0
        assert all(isinstance(f, SpectralFrame) for f in frames)

    def test_S2_2_times_non_decreasing(self, analyzer, synthetic_audio_file):
        frames = analyzer.analyze_audio(str(synthetic_audio_file))
        times = [f.time for f in frames]
        assert all(t2 >= t1 for t1, t2 in zip(times, times[1:]))

    def test_S2_3_first_time_zero(self, analyzer, synthetic_audio_file):
        frames = analyzer.analyze_audio(str(synthetic_audio_file))
        assert frames[0].time == pytest.approx(0.0, abs=1e-6)

    def test_S2_4_all_finite(self, analyzer, synthetic_audio_file):
        frames = analyzer.analyze_audio(str(synthetic_audio_file))
        for f in frames:
            for field in ("time", "centroid", "flux", "rolloff", "flatness",
                          "bandwidth", "rms", "onset_strength"):
                v = getattr(f, field)
                assert np.isfinite(v), f"{field} not finite"


# --- analyze_audio_to_arrays ----------------------------------------------

class TestAnalyzeAudioToArrays:
    def test_S3_1_has_all_keys(self, analyzer, synthetic_audio_file):
        arrs = analyzer.analyze_audio_to_arrays(str(synthetic_audio_file))
        for k in ("times", "centroid", "flux", "rolloff", "flatness",
                  "bandwidth", "rms", "onset_strength"):
            assert k in arrs

    def test_S3_2_all_same_length(self, analyzer, synthetic_audio_file):
        arrs = analyzer.analyze_audio_to_arrays(str(synthetic_audio_file))
        lens = {k: len(v) for k, v in arrs.items()}
        assert len(set(lens.values())) == 1
        assert all(n >= 1 for n in lens.values())

    def test_S3_3_times_non_decreasing(self, analyzer, synthetic_audio_file):
        arrs = analyzer.analyze_audio_to_arrays(str(synthetic_audio_file))
        assert np.all(np.diff(arrs["times"]) >= 0)

    def test_S3_4_all_finite(self, analyzer, synthetic_audio_file):
        arrs = analyzer.analyze_audio_to_arrays(str(synthetic_audio_file))
        for k, v in arrs.items():
            assert np.all(np.isfinite(v)), f"{k} not finite"

    def test_S3_5_flux_starts_at_zero(self, analyzer, synthetic_audio_file):
        arrs = analyzer.analyze_audio_to_arrays(str(synthetic_audio_file))
        assert arrs["flux"][0] == 0.0


# --- get_note_profile ------------------------------------------------------

class TestGetNoteProfile:
    def test_S4_1_default_when_out_of_range(self, analyzer, synthetic_audio_arrays):
        # Window past end of audio
        last_t = synthetic_audio_arrays["times"][-1]
        p = analyzer.get_note_profile(synthetic_audio_arrays,
                                       last_t + 100, last_t + 101)
        assert p.brightness == 0.5
        assert p.attack == 0.5
        assert p.richness == 0.5
        assert p.warmth == 0.5
        assert p.flux == 0.5
        np.testing.assert_array_equal(p.dynamic_envelope, np.array([0.5]))

    def test_S4_2_attack_is_max_onset(self, analyzer, synthetic_audio_arrays):
        # Carve a region and check attack is max of onset_strength slice.
        onset = float(synthetic_audio_arrays["times"][10])
        offset = float(synthetic_audio_arrays["times"][20])
        p = analyzer.get_note_profile(synthetic_audio_arrays, onset, offset)
        mask = (synthetic_audio_arrays["times"] >= onset - 0.02) & \
               (synthetic_audio_arrays["times"] <= offset)
        expected_max = float(np.max(synthetic_audio_arrays["onset_strength"][mask]))
        assert p.attack == pytest.approx(expected_max)

    def test_S4_3_brightness_is_mean(self, analyzer, synthetic_audio_arrays):
        onset = float(synthetic_audio_arrays["times"][10])
        offset = float(synthetic_audio_arrays["times"][20])
        p = analyzer.get_note_profile(synthetic_audio_arrays, onset, offset)
        mask = (synthetic_audio_arrays["times"] >= onset - 0.02) & \
               (synthetic_audio_arrays["times"] <= offset)
        expected_mean = float(np.mean(synthetic_audio_arrays["centroid"][mask]))
        assert p.brightness == pytest.approx(expected_mean)

    def test_S4_4_envelope_is_copy(self, analyzer, synthetic_audio_arrays):
        onset = float(synthetic_audio_arrays["times"][10])
        offset = float(synthetic_audio_arrays["times"][20])
        p = analyzer.get_note_profile(synthetic_audio_arrays, onset, offset)
        p.dynamic_envelope[:] = 999.0
        assert np.any(synthetic_audio_arrays["rms"] != 999.0)


# --- compute_normalization_stats -------------------------------------------

class TestComputeNormalizationStats:
    def test_S5_1_and_S5_2_keys_and_subkeys(self, analyzer):
        profiles = [
            NoteSpectralProfile(brightness=float(i), attack=float(i),
                                richness=float(i), warmth=float(i),
                                flux=float(i))
            for i in range(20)
        ]
        stats = analyzer.compute_normalization_stats(profiles)
        for field in ("brightness", "attack", "richness", "warmth", "flux"):
            assert field in stats
            for sub in ("min", "max", "mean", "std"):
                assert sub in stats[field]
                assert isinstance(stats[field][sub], float)

    def test_S5_3_uses_percentiles(self, analyzer):
        vals = list(range(100))  # 0..99
        profiles = [
            NoteSpectralProfile(brightness=float(v), attack=float(v),
                                richness=float(v), warmth=float(v),
                                flux=float(v))
            for v in vals
        ]
        stats = analyzer.compute_normalization_stats(profiles)
        # 2nd percentile of 0..99 ≈ 1.98, 98th ≈ 97.02
        assert stats["brightness"]["min"] == pytest.approx(np.percentile(vals, 2))
        assert stats["brightness"]["max"] == pytest.approx(np.percentile(vals, 98))


# --- normalize_profile -----------------------------------------------------

class TestNormalizeProfile:
    def _stats(self, lo=0.0, hi=10.0):
        return {
            f: {"min": lo, "max": hi, "mean": (lo + hi) / 2, "std": 1.0}
            for f in ("brightness", "attack", "richness", "warmth", "flux")
        }

    def test_S6_1_outputs_in_unit_range(self, analyzer):
        stats = self._stats(0.0, 10.0)
        # Value well inside range
        p = NoteSpectralProfile(brightness=5.0, attack=5.0, richness=5.0,
                                warmth=5.0, flux=5.0)
        n = analyzer.normalize_profile(p, stats)
        for v in (n.brightness, n.attack, n.richness, n.warmth, n.flux):
            assert 0.0 <= v <= 1.0

        # Value above max should clamp to 1 (warmth inverts, clamps to 0)
        p2 = NoteSpectralProfile(brightness=100.0, attack=100.0, richness=100.0,
                                 warmth=100.0, flux=100.0)
        n2 = analyzer.normalize_profile(p2, stats)
        for v in (n2.brightness, n2.attack, n2.richness, n2.warmth, n2.flux):
            assert 0.0 <= v <= 1.0

    def test_S6_2_warmth_inverted(self, analyzer):
        stats = self._stats(0.0, 10.0)
        # Low raw rolloff → high warmth
        p_low = NoteSpectralProfile(brightness=0, attack=0, richness=0,
                                    warmth=0.0, flux=0)
        p_high = NoteSpectralProfile(brightness=0, attack=0, richness=0,
                                     warmth=10.0, flux=0)
        n_low = analyzer.normalize_profile(p_low, stats)
        n_high = analyzer.normalize_profile(p_high, stats)
        assert n_low.warmth == pytest.approx(1.0)
        assert n_high.warmth == pytest.approx(0.0)

    def test_S6_3_degenerate_range_returns_half(self, analyzer):
        stats = self._stats(5.0, 5.0)  # degenerate
        p = NoteSpectralProfile(brightness=5.0, attack=5.0, richness=5.0,
                                warmth=5.0, flux=5.0)
        n = analyzer.normalize_profile(p, stats)
        for v in (n.brightness, n.attack, n.richness, n.flux):
            assert v == 0.5
        # warmth = 1 - 0.5 = 0.5
        assert n.warmth == 0.5

    def test_S6_4_envelope_passthrough(self, analyzer):
        stats = self._stats(0.0, 10.0)
        env = np.array([0.1, 0.2, 0.3], dtype=np.float32)
        p = NoteSpectralProfile(brightness=5, attack=5, richness=5,
                                warmth=5, flux=5, dynamic_envelope=env)
        n = analyzer.normalize_profile(p, stats)
        np.testing.assert_array_equal(n.dynamic_envelope, env)


# --- SpectralTrajectory ----------------------------------------------------

class TestSpectralTrajectoryInit:
    def test_S7_1_empty_arrays(self):
        empty = {
            "times": np.array([]),
            "centroid": np.array([]), "flux": np.array([]),
            "rolloff": np.array([]), "flatness": np.array([]),
            "bandwidth": np.array([]), "rms": np.array([]),
            "onset_strength": np.array([]),
        }
        t = SpectralTrajectory(empty)
        assert t.trajectory_times.size == 0
        assert t.trajectories == {}

    def test_S7_2_keys(self, synthetic_audio_arrays):
        t = SpectralTrajectory(synthetic_audio_arrays, window_sec=0.5, hop_sec=0.1)
        for k in ("centroid", "flux", "rolloff", "flatness", "bandwidth", "rms"):
            assert k in t.trajectories

    def test_S7_3_entries_have_mean_std_delta(self, synthetic_audio_arrays):
        t = SpectralTrajectory(synthetic_audio_arrays, window_sec=0.5, hop_sec=0.1)
        for feat, entries in t.trajectories.items():
            for entry in entries:
                assert set(entry.keys()) == {"mean", "std", "delta"}
                for v in entry.values():
                    assert isinstance(v, float)

    def test_S7_4_times_non_decreasing(self, synthetic_audio_arrays):
        t = SpectralTrajectory(synthetic_audio_arrays, window_sec=0.5, hop_sec=0.1)
        if len(t.trajectory_times) > 1:
            assert np.all(np.diff(t.trajectory_times) >= 0)


class TestGetContextAt:
    def test_S8_1_keys(self, synthetic_audio_arrays):
        t = SpectralTrajectory(synthetic_audio_arrays, window_sec=0.5, hop_sec=0.1)
        ctx = t.get_context_at(1.0)
        for feat in ("centroid", "flux", "rolloff", "flatness", "bandwidth", "rms"):
            assert feat in ctx
            assert set(ctx[feat].keys()) == {"mean", "std", "delta"}

    def test_S8_2_empty_trajectory_defaults(self):
        empty = {
            "times": np.array([]),
            "centroid": np.array([]), "flux": np.array([]),
            "rolloff": np.array([]), "flatness": np.array([]),
            "bandwidth": np.array([]), "rms": np.array([]),
            "onset_strength": np.array([]),
        }
        t = SpectralTrajectory(empty)
        ctx = t.get_context_at(0.0)
        for feat, entry in ctx.items():
            assert entry["mean"] == 0.5
            assert entry["std"] == 0.0
            assert entry["delta"] == 0.0

    def test_S8_3_out_of_range_clamps(self, synthetic_audio_arrays):
        t = SpectralTrajectory(synthetic_audio_arrays, window_sec=0.5, hop_sec=0.1)
        # Far past the end shouldn't raise
        t.get_context_at(1e6)
        t.get_context_at(-1e6)


class TestToEmbedding:
    def test_S9_1_exact_dim(self, synthetic_audio_arrays):
        t = SpectralTrajectory(synthetic_audio_arrays, window_sec=0.5, hop_sec=0.1)
        for dim in (4, 16, 32):
            emb = t.to_embedding(1.0, dim=dim)
            assert emb.shape == (dim,)

    def test_S9_2_dtype_float32(self, synthetic_audio_arrays):
        t = SpectralTrajectory(synthetic_audio_arrays, window_sec=0.5, hop_sec=0.1)
        emb = t.to_embedding(1.0, dim=16)
        assert emb.dtype == np.float32

    def test_S9_3_finite(self, synthetic_audio_arrays):
        t = SpectralTrajectory(synthetic_audio_arrays, window_sec=0.5, hop_sec=0.1)
        emb = t.to_embedding(1.0, dim=16)
        assert np.all(np.isfinite(emb))

    def test_S9_4_pads_and_truncates(self, synthetic_audio_arrays):
        t = SpectralTrajectory(synthetic_audio_arrays, window_sec=0.5, hop_sec=0.1)
        small = t.to_embedding(1.0, dim=4)
        big = t.to_embedding(1.0, dim=64)
        assert small.shape == (4,)
        assert big.shape == (64,)
        # The tail of the padded embedding (beyond the natural 18) is zero.
        assert np.all(big[18:] == 0.0)

    def test_S9_5_empty_trajectory(self):
        empty = {
            "times": np.array([]),
            "centroid": np.array([]), "flux": np.array([]),
            "rolloff": np.array([]), "flatness": np.array([]),
            "bandwidth": np.array([]), "rms": np.array([]),
            "onset_strength": np.array([]),
        }
        t = SpectralTrajectory(empty)
        emb = t.to_embedding(0.0, dim=16)
        assert emb.shape == (16,)
        assert np.all(np.isfinite(emb))


# --- additional clause coverage -------------------------------------------

class TestSpectralFrameFields:
    def test_S0_1_all_fields_are_float(self):
        """S0.1: SpectralFrame fields are plain floats."""
        from spectral import SpectralFrame
        f = SpectralFrame(time=0.0, centroid=1000.0, flux=0.1, rolloff=2000.0,
                          flatness=0.3, bandwidth=500.0, rms=0.5,
                          onset_strength=1.2)
        for field in ("time", "centroid", "flux", "rolloff", "flatness",
                      "bandwidth", "rms", "onset_strength"):
            assert isinstance(getattr(f, field), float)


class TestNoteSpectralProfileFields:
    def test_S0_2_scalar_fields_are_float_envelope_is_ndarray(self):
        """S0.2: NoteSpectralProfile scalar fields are floats; envelope is ndarray."""
        p = NoteSpectralProfile(brightness=0.5, attack=0.5, richness=0.5,
                                warmth=0.5, flux=0.5)
        for field in ("brightness", "attack", "richness", "warmth", "flux"):
            assert isinstance(getattr(p, field), float)
        assert isinstance(p.dynamic_envelope, np.ndarray)


class TestGetNoteProfileLookback:
    def test_S4_5_attack_window_includes_lookback(self, synthetic_audio_arrays):
        """S4.5: profile window starts 20ms before onset to capture attack."""
        analyzer = SpectralAnalyzer()
        onset = float(synthetic_audio_arrays["times"][20])
        offset = float(synthetic_audio_arrays["times"][25])
        lookback = 0.02
        times = synthetic_audio_arrays["times"]
        mask_with = (times >= onset - lookback) & (times <= offset)
        mask_without = (times >= onset) & (times <= offset)
        p = analyzer.get_note_profile(synthetic_audio_arrays, onset, offset)
        if mask_with.sum() > mask_without.sum():
            expected = float(np.max(
                synthetic_audio_arrays["onset_strength"][mask_with]))
            assert p.attack == pytest.approx(expected)

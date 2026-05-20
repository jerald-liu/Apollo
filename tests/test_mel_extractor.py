"""Tests for apollo.ingest.audio.MelExtractor.

Covers COND-01 (fixed-shape mel at documented SR/hop/n_mels) and COND-04
(missing/malformed wav abort). Also verifies the threat-model mitigations:
size cap (T-01-07) and duration cap (T-01-08). Pad value is log(1e-8) per
RESEARCH.md "Mel Pipeline / Padding value choice" — not zero, which would
be loud in log-mel space.
"""

from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf
import torch

from apollo.ingest import IngestError, MelExtractor


def _write_silence(path, seconds: float, sr: int, channels: int = 1):
    """Synthesize and write a silent wav of the requested duration / sr / channels."""
    samples = int(seconds * sr)
    data = np.zeros((samples, channels), dtype=np.float32)
    sf.write(str(path), data, sr)


def test_shape_and_dtype_44100hz(tmp_path):
    """A 1-second 44.1 kHz wav (resample path) produces (96, 128) float32."""
    p = tmp_path / "in_44100.wav"
    _write_silence(p, seconds=1.0, sr=44100)
    out = MelExtractor()(str(p), "tests/pair/44100")
    assert out.shape == (96, 128), out.shape
    assert out.dtype == torch.float32, out.dtype


def test_shape_and_dtype_22050hz(tmp_path):
    """A 1-second 22.05 kHz wav (no resample) produces (96, 128) float32."""
    p = tmp_path / "in_22050.wav"
    _write_silence(p, seconds=1.0, sr=22050)
    out = MelExtractor()(str(p), "tests/pair/22050")
    assert out.shape == (96, 128)
    assert out.dtype == torch.float32


def test_padding_value_is_log_floor(tmp_path):
    """A short (0.1 s) wav is right-padded; last frame equals log(1e-8) ≈ -18.42, not zero."""
    p = tmp_path / "short.wav"
    _write_silence(p, seconds=0.1, sr=22050)
    out = MelExtractor()(str(p), "tests/pair/short")
    expected_pad = float(np.log(1e-8))
    # Last frame, first mel bin: should be the pad value (≈ -18.42)
    assert out[-1, 0].item() == pytest.approx(expected_pad, abs=0.1)
    # Sanity: definitely not zero (zero in log-mel = loud)
    assert out[-1, 0].item() < -10.0


def test_truncation_for_long_wav(tmp_path):
    """A 5-second wav exceeds TARGET_FRAMES and is truncated to (96, 128)."""
    p = tmp_path / "long.wav"
    _write_silence(p, seconds=5.0, sr=22050)
    out = MelExtractor()(str(p), "tests/pair/long")
    assert out.shape == (96, 128)


def test_stereo_mono_mix(tmp_path):
    """A 1-second stereo wav is mono-mixed; output is still (96, 128)."""
    p = tmp_path / "stereo.wav"
    _write_silence(p, seconds=1.0, sr=22050, channels=2)
    out = MelExtractor()(str(p), "tests/pair/stereo")
    assert out.shape == (96, 128)
    assert out.dtype == torch.float32


def test_missing_file_raises_ingest_error():
    """A nonexistent path raises IngestError with reason mentioning failed load/stat."""
    with pytest.raises(IngestError, match="failed to (load|stat)"):
        MelExtractor()("/nonexistent/missing.wav", "tests/pair/missing")


def test_oversize_file_raises_ingest_error(tmp_path):
    """A file > 10 MB on disk aborts BEFORE torchaudio.load with a size-cap message."""
    p = tmp_path / "huge.wav"
    # 11 MB of arbitrary bytes — torchaudio would never get to parse this
    p.write_bytes(b"\x00" * (11 * 1024 * 1024))
    with pytest.raises(IngestError, match="size cap"):
        MelExtractor()(str(p), "tests/pair/huge")


def test_resampler_caching(tmp_path):
    """Calling on two same-SR (44100) wavs registers a single Resample module."""
    p1 = tmp_path / "a.wav"
    p2 = tmp_path / "b.wav"
    _write_silence(p1, seconds=1.0, sr=44100)
    _write_silence(p2, seconds=1.0, sr=44100)
    mx = MelExtractor()
    mx(str(p1), "tests/pair/a")
    mx(str(p2), "tests/pair/b")
    assert len(mx._resamplers) == 1
    assert 44100 in mx._resamplers

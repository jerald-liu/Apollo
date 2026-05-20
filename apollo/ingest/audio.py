"""Mel-feature extraction for `call.wav`.

Reads a wav, downsamples to 22050 Hz, runs torchaudio MelSpectrogram
(n_mels=128, n_fft=2048, hop=512), log-compresses, and pads/truncates to
a fixed (96, 128) float32 tensor — the contract Phase 2's mel encoder
consumes per D-14.

See .planning/phases/01-tokenizer-ingest/01-RESEARCH.md §"Mel Pipeline"
for the design rationale and §"Open Risks #4" (power=2.0). Threat model
mitigations T-01-07 (file size cap) and T-01-08 (duration cap) are
enforced before / after torchaudio.load respectively.
"""

from __future__ import annotations

import os

import numpy as np
import soundfile as sf
import torch
import torchaudio
from torchaudio.transforms import MelSpectrogram, Resample

from apollo.ingest.errors import IngestError


class MelExtractor:
    """Callable that turns a `call.wav` into a fixed-shape log-mel tensor.

    Usage:
        mx = MelExtractor()
        log_mel = mx("data/pairs/001/call.wav", "data/pairs/001")  # (96, 128) float32
    """

    # ---- Mel / audio config (D-11, D-12, D-13) ----
    TARGET_SR = 22050
    N_FFT = 2048
    HOP_LENGTH = 512
    N_MELS = 128
    TARGET_FRAMES = 96
    LOG_FLOOR = 1e-8

    # ---- Security caps (T-01-07, T-01-08) ----
    MAX_WAV_BYTES = 10 * 1024 * 1024  # 10 MB
    MAX_WAV_SECONDS = 30.0

    def __init__(self) -> None:
        # Cached MelSpectrogram — instantiated once, reused across pairs.
        self.mel = MelSpectrogram(
            sample_rate=self.TARGET_SR,
            n_fft=self.N_FFT,
            hop_length=self.HOP_LENGTH,
            n_mels=self.N_MELS,
            power=2.0,
            center=True,
            mel_scale="htk",
        )
        # Resample modules cached per source SR — corpus is mostly 44.1/48 kHz,
        # so this typically holds 1–2 entries for the whole run.
        self._resamplers: dict[int, Resample] = {}

    def __call__(self, wav_path: str, pair_path: str) -> torch.Tensor:
        # --- Security: reject huge files before torchaudio.load (T-01-07) ---
        try:
            size = os.path.getsize(wav_path)
        except OSError as e:
            raise IngestError(pair_path, f"failed to stat {wav_path}: {e}")
        if size > self.MAX_WAV_BYTES:
            raise IngestError(
                pair_path,
                f"wav exceeds size cap ({size} > {self.MAX_WAV_BYTES} bytes)",
            )

        # --- Load via soundfile — avoids torchaudio.load's torchcodec backend
        # dependency (torchaudio 2.8+ defaults to torchcodec on Linux; soundfile
        # is a stable, codec-free alternative for WAV/FLAC/OGG files).
        try:
            data, sr = sf.read(wav_path, dtype="float32", always_2d=True)
            wav = torch.from_numpy(data.T)  # (channels, samples) float32
        except Exception as e:
            raise IngestError(pair_path, f"failed to load {wav_path}: {e}")

        # --- Security: reject long decoded audio (T-01-08) ---
        duration = wav.shape[-1] / float(sr)
        if duration > self.MAX_WAV_SECONDS:
            raise IngestError(
                pair_path,
                f"wav duration {duration:.2f}s exceeds cap ({self.MAX_WAV_SECONDS}s)",
            )

        # Mono mix (preserves the leading dim — MelSpectrogram expects (..., samples))
        if wav.shape[0] > 1:
            wav = wav.mean(dim=0, keepdim=True)

        # Resample to target SR (cached per source SR)
        if sr != self.TARGET_SR:
            if sr not in self._resamplers:
                self._resamplers[sr] = Resample(orig_freq=sr, new_freq=self.TARGET_SR)
            wav = self._resamplers[sr](wav)

        # Mel: (1, n_mels, T) → log → (T, n_mels)
        mel = self.mel(wav)
        log_mel = torch.log(mel + self.LOG_FLOOR)
        log_mel = log_mel.squeeze(0).transpose(0, 1).contiguous()  # (T, 128)

        return self._fix_frames(log_mel, pair_path)

    def _fix_frames(self, log_mel: torch.Tensor, pair_path: str) -> torch.Tensor:
        """Pad with log(LOG_FLOOR) or truncate to (TARGET_FRAMES, N_MELS) float32."""
        T, M = log_mel.shape
        if M != self.N_MELS:
            raise IngestError(
                pair_path, f"mel produced {M} mels, expected {self.N_MELS}"
            )
        if T >= self.TARGET_FRAMES:
            return log_mel[: self.TARGET_FRAMES, :].contiguous().to(torch.float32)
        # Pad value: log(1e-8) ≈ -18.42. NOT zero — zero in log-mel space is
        # loud (power=1) and creates a step function the model would have to
        # learn to ignore. See RESEARCH.md "Padding value choice".
        pad_value = float(np.log(self.LOG_FLOOR))
        pad = torch.full(
            (self.TARGET_FRAMES - T, M), pad_value, dtype=log_mel.dtype
        )
        return torch.cat([log_mel, pad], dim=0).contiguous().to(torch.float32)

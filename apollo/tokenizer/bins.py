"""Quantization bin edges and helpers for time, velocity, and duration.

See RESEARCH.md §"Duration Bin Scheme" — D-21 locked at 24 log-spaced duration bins
from 30 ms to 1.5 s. Time is grid-locked at 32 bins of width = 32nd-note at 120 bpm
(0.03125 s/bin → 0..1.0 s range). Velocity is 16 linear bins over 1..127.

These functions raise `ValueError` on out-of-range inputs where appropriate. The
tokenizer / ingest layer is responsible for translating those into `IngestError`
with the offending pair path (D-04, D-16).
"""

from __future__ import annotations

import numpy as np


# 25 edges → 24 bins. Computed once at import time; deterministic.
DURATION_EDGES = np.logspace(np.log10(0.030), np.log10(1.500), num=25)


def quantize_duration(d_sec: float) -> int:
    """Quantize a duration in seconds to a bin index in [0, 23].

    Out-of-range inputs are clamped to the [0.030, 1.500] s window. This is
    deliberate — the model has no way to express durations outside that band,
    so silently clamping during encode is preferable to crashing on a near-edge
    note. (D-04 abort policy applies to pitch range only, not duration.)
    """
    d = max(0.030, min(1.500, d_sec))
    # searchsorted(side='right') returns 25 when d == upper edge (1.500); cap at 23.
    bin_i = int(np.searchsorted(DURATION_EDGES, d, side="right")) - 1
    return max(0, min(23, bin_i))


def decode_duration(bin_i: int) -> float:
    """Decode a duration bin index back to seconds (geometric mean of edges)."""
    lo, hi = DURATION_EDGES[bin_i], DURATION_EDGES[bin_i + 1]
    return float(np.sqrt(lo * hi))


# Time-shift quantization.
#
# Per CONTEXT.md D-05 and RESEARCH.md §"Vocab ID Layout": 32 bins at 120 bpm covering
# ~2 beats (max ≈ 1.0 s), bin width = 0.03125 s. The general formula for "n_bins per
# 2 beats at tempo_bpm" is bin_width = (60 / tempo_bpm) * 2 / n_bins. At 120 bpm with
# 32 bins this gives (60/120) * 2 / 32 = 0.03125 s ✓.
#
# (The plan's interface snippet wrote bin_width = (60/tempo_bpm)/8, which is 0.0625 s
# at 120 bpm — i.e. a 32nd-note width but on a different beat-count convention. That
# disagrees with both D-05 "32 bins ≈ 2 beats" and the inline comment "max = 1.0 s".
# We follow the spec, not the inconsistent code snippet — [Rule 1 - Bug] fix.)
def quantize_time_shift(dt_sec: float, tempo_bpm: float = 120.0, n_bins: int = 32) -> int:
    """Quantize an inter-onset time delta to a bin index in [0, n_bins).

    Raises `ValueError` if `dt_sec` falls outside [0, n_bins * bin_width). The
    tokenizer layer wraps this in `IngestError(pair_path, ...)` so the user can
    see which pair triggered the abort.
    """
    bin_width = (60.0 / tempo_bpm) * 2.0 / n_bins
    bin_i = int(round(dt_sec / bin_width))
    if bin_i < 0 or bin_i >= n_bins:
        raise ValueError(
            f"time_shift {dt_sec:.3f}s out of bin range [0, {n_bins * bin_width:.3f}s)"
        )
    return bin_i


def decode_time_shift(bin_i: int, tempo_bpm: float = 120.0, n_bins: int = 32) -> float:
    """Decode a time-shift bin index to seconds at the given tempo."""
    bin_width = (60.0 / tempo_bpm) * 2.0 / n_bins
    return bin_i * bin_width


# Velocity: 16 linear bins over 1..127. bin = (vel - 1) * 16 // 127, clamped to 0..15.
def quantize_velocity(vel: int) -> int:
    """Quantize a 1..127 MIDI velocity to a bin index in [0, 15].

    Clamps inputs outside 1..127 to the boundary bins (0 or 15).
    """
    v = max(1, min(127, int(vel)))
    return min(15, (v - 1) * 16 // 127)


def decode_velocity(bin_i: int) -> int:
    """Decode a velocity bin to its center (1-based MIDI velocity, 1..127)."""
    return int(round(1 + (bin_i + 0.5) * 127 / 16))

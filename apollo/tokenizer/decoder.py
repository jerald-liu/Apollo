"""Symbolic tokenizer decode side. Inverse of encode (up to quantization).

See RESEARCH.md §"Tokenizer Design / Decoder algorithm". The decoder consumes a
flat token stream produced by `Tokenizer.encode` (or by Phase 2's training packer,
after BOS/SEP/EOS have been stripped) and reconstructs `Note` objects with
absolute seconds-time recovered via a running cursor.

Per-slot range validation (T-01-04 mitigation) guards against corrupted streams:
each of the 4 IDs per note must fall in its dedicated [offset, offset+N) window
or the function raises `ValueError`. The caller decides whether to wrap that in
an `IngestError` (artifact load path) or surface it directly (round-trip tests).
"""

from __future__ import annotations

from typing import List

from apollo.tokenizer.bins import (
    decode_duration,
    decode_time_shift,
    decode_velocity,
)
from apollo.tokenizer.vocab import Vocab


def decode_tokens(ids: List[int], vocab: Vocab, tempo_bpm: float = 120.0):
    """Decode a flat token list to a list of `Note`.

    Each note consumes 4 IDs: [time_shift, pitch, velocity, duration]. Trailing
    partial groups (fewer than 4 IDs left at the tail) are dropped silently —
    the encoder never emits them, and Phase 2's packer is responsible for
    stripping BOS/SEP/EOS before calling decode. Per-slot range validation
    catches corruption (e.g. a velocity token landing in the pitch slot).
    """
    # Local import avoids circular dependency with encoder.py.
    from apollo.tokenizer.encoder import Note

    v = vocab
    notes: List[Note] = []
    cursor = 0.0
    i = 0
    while i + 3 < len(ids):
        t_id, p_id, vel_id, d_id = ids[i], ids[i + 1], ids[i + 2], ids[i + 3]

        if not (v.TIME_OFFSET <= t_id < v.TIME_OFFSET + v.N_TIME):
            raise ValueError(f"token at pos {i} ({t_id}) not in time range")
        if not (v.PITCH_OFFSET <= p_id < v.PITCH_OFFSET + v.N_PITCH):
            raise ValueError(f"token at pos {i + 1} ({p_id}) not in pitch range")
        if not (v.VELOCITY_OFFSET <= vel_id < v.VELOCITY_OFFSET + v.N_VELOCITY):
            raise ValueError(f"token at pos {i + 2} ({vel_id}) not in velocity range")
        if not (v.DURATION_OFFSET <= d_id < v.DURATION_OFFSET + v.N_DURATION):
            raise ValueError(f"token at pos {i + 3} ({d_id}) not in duration range")

        dt = decode_time_shift(t_id - v.TIME_OFFSET, tempo_bpm=tempo_bpm)
        cursor += dt
        dur = decode_duration(d_id - v.DURATION_OFFSET)
        notes.append(
            Note(
                pitch=v.PITCH_MIN + (p_id - v.PITCH_OFFSET),
                velocity=decode_velocity(vel_id - v.VELOCITY_OFFSET),
                start=cursor,
                end=cursor + dur,
            )
        )
        i += 4
    return notes

"""Symbolic tokenizer encode side.

See .planning/phases/01-tokenizer-ingest/01-RESEARCH.md §"Tokenizer Design" for the
full design (4-tokens-per-note packing, encoder algorithm, decoder algorithm).

Per-note packing is `[time_shift, pitch, velocity, duration]` (D-07). Encoder emits
raw note tokens only — BOS / SEP / EOS wrapping is the training packer's job
(Phase 2, per D-08), not this module's.

Out-of-range pitch (D-04) and over-window time_shift abort with `IngestError` so
the caller can see exactly which pair file triggered the failure. No silent
clipping for pitch; duration clamps inside `bins.quantize_duration` because the
model has no representation for durations outside the 30 ms..1.5 s band.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from apollo.ingest.errors import IngestError
from apollo.tokenizer.bins import (
    quantize_duration,
    quantize_time_shift,
    quantize_velocity,
)
from apollo.tokenizer.vocab import Vocab


@dataclass
class Note:
    """A single MIDI note event in seconds-time, raw (un-quantized) values.

    `pitch` is the MIDI number (not a bin index). `velocity` is 1..127.
    `start` and `end` are absolute seconds within the local pair (call or
    response side); the tokenizer turns the inter-onset delta into a
    time_shift token at encode time and reconstructs absolute time via a
    cursor at decode time.
    """

    pitch: int
    velocity: int
    start: float
    end: float


class Tokenizer:
    """Notes ↔ token IDs. See RESEARCH.md §"Tokenizer Design"."""

    def __init__(
        self,
        vocab: Vocab,
        tempo_bpm: float = 120.0,
        pair_path: str = "<unknown>",
    ):
        self.vocab = vocab
        self.tempo_bpm = tempo_bpm
        self.pair_path = pair_path
        # Time bin = 32nd-note at tempo_bpm; 32 bins covers ~2 beats. This
        # mirrors apollo.tokenizer.bins.quantize_time_shift, which uses
        # bin_width = (60 / bpm) * 2 / n_bins = 0.03125 s at 120 bpm, 32 bins.
        # We compute time_max_sec here purely to give a precise IngestError
        # message before quantize_time_shift's ValueError fires.
        self.time_max_sec = (60.0 / tempo_bpm) * 2.0  # = n_bins * bin_width

    def encode(self, notes: List[Note]) -> List[int]:
        """Encode notes to a flat list of token IDs (4 per note).

        Raises `IngestError` on:
          - out-of-order notes (negative inter-onset delta)
          - inter-onset delta >= time_max_sec (32 bins of 32nd-notes)
          - pitch outside `[Vocab.PITCH_MIN, Vocab.PITCH_MAX]`
          - any other quantizer ValueError (wrapped, path attached)
        """
        v = self.vocab
        prev_onset = 0.0
        tokens: List[int] = []
        for note in notes:
            dt = note.start - prev_onset
            if dt < 0:
                raise IngestError(
                    self.pair_path,
                    f"notes out of order: negative time_shift {dt:.3f}s",
                )
            if dt >= self.time_max_sec:
                raise IngestError(
                    self.pair_path,
                    f"time_shift {dt:.3f}s exceeds vocab range "
                    f"(max {self.time_max_sec:.3f}s)",
                )
            if not (v.PITCH_MIN <= note.pitch <= v.PITCH_MAX):
                raise IngestError(
                    self.pair_path,
                    f"pitch {note.pitch} outside C2-C5 window "
                    f"(allowed: {v.PITCH_MIN}-{v.PITCH_MAX})",
                )
            # Bin 0 is valid (per Open Risks #5): the first note's dt is 0.0,
            # which round-trips to bin 0 → cursor stays at 0 on decode.
            try:
                t_bin = quantize_time_shift(
                    dt, tempo_bpm=self.tempo_bpm, n_bins=v.N_TIME
                )
            except ValueError as e:
                raise IngestError(self.pair_path, str(e))

            tokens.append(v.TIME_OFFSET + t_bin)
            tokens.append(v.PITCH_OFFSET + (note.pitch - v.PITCH_MIN))
            tokens.append(v.VELOCITY_OFFSET + quantize_velocity(note.velocity))
            tokens.append(v.DURATION_OFFSET + quantize_duration(note.end - note.start))
            prev_onset = note.start
        return tokens

    def decode(self, ids: List[int]) -> List[Note]:
        """Decode token IDs to notes (inverse of encode, up to quantization)."""
        # Local import avoids circular dependency: decoder.py imports Note from here.
        from apollo.tokenizer.decoder import decode_tokens

        return decode_tokens(ids, self.vocab, self.tempo_bpm)

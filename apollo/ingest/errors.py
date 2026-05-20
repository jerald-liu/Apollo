"""IngestError — the single exception raised by the ingest pipeline.

Raised on any pair-level ingest failure: missing/malformed call.wav, missing
call.mid or response.mid, out-of-range pitch (D-04), overlapping notes in a
monophonic file, time-shift outside the quantization window, or schema
mismatch. Carries `pair_path` so the operator can see which pair to fix.

See decisions D-04 (pitch range abort), D-16 (missing audio abort), COND-04
(error reporting policy).
"""

from __future__ import annotations


class IngestError(Exception):
    """Raised on any pair-level ingest failure (D-04, D-16, COND-04)."""

    def __init__(self, pair_path: str, reason: str):
        self.pair_path = pair_path
        self.reason = reason
        super().__init__(f"[{pair_path}] {reason}")

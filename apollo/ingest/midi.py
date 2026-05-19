"""MIDI file loading with monophonic / single-instrument / tempo guards.

Wraps `pretty_midi` to produce `apollo.tokenizer.Note` lists from `.mid`
files. Enforces the corpus invariants captured in RESEARCH.md §"Library
Recommendations / MIDI parsing", §"Common Pitfalls #1", and §"Open Risks
#1, #3, #6, #7":

  - Exactly one instrument track (#7)
  - Tempo within ±2 bpm of the configured `tempo_bpm` (#3)
  - At least one note (#6 — empty MIDI → abort, not silent success)
  - Notes sorted by start (pretty_midi preserves file order, not time order)
  - Monophonic non-overlap with floating-point slop EPS = 1e-3 s
  - DoS cap of `MAX_NOTES_PER_PAIR` to bound per-file work (T-01-12)

All failures raise `IngestError(pair_path, reason)` so the operator can
see exactly which pair to fix.
"""

from __future__ import annotations

from typing import List

import pretty_midi

from apollo.ingest.errors import IngestError
from apollo.tokenizer.types import Note


# Maximum number of notes accepted from a single `.mid` file. Threat model
# mitigation T-01-12 (denial-of-service via pathological MIDI). 1000 is far
# above the v1 "tiny gesture" upper bound (~6 notes per side).
MAX_NOTES_PER_PAIR = 1000

# Floating-point slop for monophonic overlap detection: pretty_midi converts
# ticks to seconds, which can produce sub-millisecond drift at note boundaries.
MONOPHONIC_EPS = 1e-3  # seconds

# Tempo tolerance (RESEARCH §"Open Risks #3"): authoring drift below ±2 bpm
# keeps time-bin alignment intact. Outside the band, time quantization is
# unsafe and we abort.
TEMPO_TOLERANCE_BPM = 2.0


def load_notes(
    mid_path: str, pair_path: str, tempo_bpm: float = 120.0
) -> List[Note]:
    """Load a `.mid` file into a list of `Note` objects, sorted by start.

    Raises `IngestError` on:
      - parse failure
      - != 1 instrument track
      - estimated tempo more than `TEMPO_TOLERANCE_BPM` from `tempo_bpm`
      - zero notes
      - > `MAX_NOTES_PER_PAIR` notes
      - any pair of adjacent (after sort) notes that overlap by more than
        `MONOPHONIC_EPS` seconds
    """
    try:
        pm = pretty_midi.PrettyMIDI(str(mid_path))
    except Exception as e:
        raise IngestError(pair_path, f"failed to parse {mid_path}: {e}")

    # Single instrument only (Open Risks #7).
    if len(pm.instruments) != 1:
        raise IngestError(
            pair_path,
            f"expected single instrument in {mid_path}, got {len(pm.instruments)}",
        )

    pm_notes = list(pm.instruments[0].notes)

    # Empty MIDI → abort (Open Risks #6). Check before tempo so the error
    # message points at the structural problem rather than a tempo artifact
    # (pretty_midi.estimate_tempo raises on empty files).
    if len(pm_notes) == 0:
        raise IngestError(pair_path, f"no notes in {mid_path}")

    # DoS cap (T-01-12).
    if len(pm_notes) > MAX_NOTES_PER_PAIR:
        raise IngestError(
            pair_path,
            f"{mid_path} has {len(pm_notes)} notes; cap is {MAX_NOTES_PER_PAIR}",
        )

    # Tempo check (Open Risks #3). estimate_tempo can still raise on edge
    # cases (e.g. a single note with no tempo marker) — treat as "tempo
    # equals configured" rather than abort, since the single-note case is
    # already trivially aligned to any tempo.
    try:
        est_tempo = float(pm.estimate_tempo())
    except Exception:
        est_tempo = tempo_bpm
    if abs(est_tempo - tempo_bpm) > TEMPO_TOLERANCE_BPM:
        raise IngestError(
            pair_path,
            f"tempo {est_tempo:.1f} bpm differs from corpus tempo "
            f"{tempo_bpm:.1f} bpm by more than ±{TEMPO_TOLERANCE_BPM} bpm",
        )

    # pretty_midi does NOT guarantee start-sorted order (Common Pitfalls #1).
    pm_notes.sort(key=lambda n: n.start)

    # Monophonic enforcement: any adjacent pair where the previous note's
    # end exceeds the next note's start (beyond EPS) is a polyphony bug.
    for i in range(len(pm_notes) - 1):
        if pm_notes[i].end > pm_notes[i + 1].start + MONOPHONIC_EPS:
            raise IngestError(
                pair_path,
                f"overlapping notes in {mid_path} — corpus is monophonic",
            )

    return [
        Note(
            pitch=n.pitch,
            velocity=n.velocity,
            start=float(n.start),
            end=float(n.end),
        )
        for n in pm_notes
    ]

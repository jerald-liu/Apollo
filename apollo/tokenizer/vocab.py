"""Frozen vocab constants — the single source of truth for token IDs.

These integer values are the contract between the tokenizer, ingest pipeline, model
embedding table, training packer, and any future inference / evaluation code. Every
downstream module imports `Vocab` from here.

Layout (see RESEARCH.md §"Vocab ID Layout"):

    [0   .. 31 ] TIME_SHIFT  (32 bins,  TIME_OFFSET=0)
    [32  .. 68 ] PITCH       (37 pitches, C2..C5, PITCH_OFFSET=32)
    [69  .. 84 ] VELOCITY    (16 bins, VELOCITY_OFFSET=69)
    [85  .. 108] DURATION    (24 log-spaced bins, DURATION_OFFSET=85)
    [109]       BOS
    [110]       EOS
    [111]       SEP
    [112 .. 255] reserved    (144 future expression-token slots — pitch bend, mod
                              wheel, CC family — allocated but unused in v1)

Active v1 vocab = 112 IDs (`0..111`). Total embedding-table allocation = 256.

Do not mutate these values without bumping `schema_version` in the pre-tokenized
artifact format. Any change here invalidates every existing checkpoint.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Vocab:
    PITCH_MIN: int = 36          # C2
    PITCH_MAX: int = 72          # C5
    N_PITCH: int = 37
    N_TIME: int = 32
    N_VELOCITY: int = 16
    N_DURATION: int = 24

    TIME_OFFSET: int = 0
    PITCH_OFFSET: int = 32
    VELOCITY_OFFSET: int = 69
    DURATION_OFFSET: int = 85

    BOS: int = 109
    EOS: int = 110
    SEP: int = 111

    VOCAB_SIZE: int = 256
    ACTIVE_VOCAB: int = 112

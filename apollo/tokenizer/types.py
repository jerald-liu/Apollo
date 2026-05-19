"""Leaf types for the tokenizer.

This module exists purely to break the circular import between
`apollo.tokenizer.encoder` and `apollo.ingest.midi`:

    apollo.tokenizer.__init__
      -> apollo.tokenizer.encoder
        -> apollo.ingest.errors (triggers apollo.ingest.__init__)
          -> apollo.ingest.artifact -> apollo.ingest.midi
            -> apollo.tokenizer.encoder  # partially initialized → ImportError

By sourcing `Note` from this leaf module (which imports nothing from
`apollo.ingest`), both `encoder.py` and `midi.py` can pull it in safely
regardless of import order.
"""

from __future__ import annotations

from dataclasses import dataclass


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

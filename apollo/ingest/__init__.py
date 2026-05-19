"""Apollo ingest package — pair discovery, MIDI/audio loading, error type.

Public surface: `IngestError` (exception) and `MelExtractor` (fixed-shape
mel-feature extractor). Additional loaders (midi.py, pairs.py, split.py,
artifact.py) land in later plans (01-04, 01-05).
"""

from .audio import MelExtractor
from .errors import IngestError

__all__ = ["IngestError", "MelExtractor"]

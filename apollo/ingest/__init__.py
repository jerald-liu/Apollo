"""Apollo ingest package — pair discovery, MIDI/audio loading, error type.

Public surface for now is just the exception type. Loaders (audio.py, midi.py,
pairs.py, split.py, artifact.py) land in later plans (01-02..01-05).
"""

from .errors import IngestError

__all__ = ["IngestError"]

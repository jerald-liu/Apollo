"""Apollo ingest package — pair discovery, MIDI/audio loading, split, artifact.

Public surface:
    - IngestError          (exception used throughout the pipeline)
    - MelExtractor         (callable: wav_path, pair_path -> Tensor(96, 128))
    - discover_pairs       (root -> List[PairPath])
    - PairPath             (dataclass of validated paths)
    - load_notes           (mid_path, pair_path -> List[Note])
    - is_heldout           (nnn -> bool, deterministic via sha1)
    - normalize_nnn        (nnn -> canonical str)
    - ingest               (root -> artifact dict)
    - save_artifact        (dict, out_path -> None)
    - load_artifact        (in_path -> dict)
    - SCHEMA_VERSION       (int constant; current = 1)
"""

from .artifact import SCHEMA_VERSION, ingest, load_artifact, save_artifact
from .audio import MelExtractor
from .errors import IngestError
from .midi import load_notes
from .pairs import PairPath, discover_pairs
from .split import is_heldout, normalize_nnn

__all__ = [
    "IngestError",
    "MelExtractor",
    "discover_pairs",
    "PairPath",
    "load_notes",
    "is_heldout",
    "normalize_nnn",
    "ingest",
    "save_artifact",
    "load_artifact",
    "SCHEMA_VERSION",
]

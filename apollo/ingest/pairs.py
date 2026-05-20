"""Pair folder discovery + per-pair file validation.

Scans `<root>/NNN/` subdirectories, validates that each contains the three
required files (`call.mid`, `call.wav`, `response.mid`), and returns a
deterministic, sorted list of `PairPath` records. NNN gaps are allowed
(D-17 — pairs are addressed by NNN, not by sequence position).

Threat-model mitigations enforced here:
- T-01-11 (path traversal): each entry's symlinks are resolved via
  `Path.resolve()` and verified to remain under the corpus root.
- T-01-16 (empty / malformed NNN): folders whose names start with `.` are
  skipped (hidden / metadata dirs).

See .planning/phases/01-tokenizer-ingest/01-RESEARCH.md §"Module Layout"
and §"Error Handling / Call sites".
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

from apollo.ingest.errors import IngestError


@dataclass(frozen=True)
class PairPath:
    """Validated paths for a single corpus pair.

    All three file paths are absolute, with symlinks resolved.
    """

    nnn: str
    dir: Path
    call_mid: Path
    call_wav: Path
    response_mid: Path


def discover_pairs(root: str) -> List[PairPath]:
    """Scan `<root>/NNN/` subdirs and return a sorted list of `PairPath`.

    Each pair must contain `call.mid`, `call.wav`, and `response.mid`;
    a missing file raises `IngestError(pair_path, "missing <filename>")`.
    Symlinks escaping the corpus root raise
    `IngestError(pair_path, "path traversal: symlink escapes corpus root")`.

    The returned list is sorted by `nnn` string for reproducibility — the
    ingest pipeline downstream relies on this ordering to produce a
    deterministic artifact across runs.
    """
    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise IngestError(
            str(root_path), "corpus root not found or not a directory"
        )

    pairs: List[PairPath] = []
    for entry in sorted(root_path.iterdir(), key=lambda p: p.name):
        if not entry.is_dir():
            continue
        nnn = entry.name
        if not nnn or nnn.startswith("."):
            continue

        # Path traversal mitigation (T-01-11): resolve symlinks and verify
        # the resolved path is still inside root_path. If not, abort.
        resolved = entry.resolve()
        try:
            resolved.relative_to(root_path)
        except ValueError:
            raise IngestError(
                str(entry), "path traversal: symlink escapes corpus root"
            )

        call_mid = resolved / "call.mid"
        call_wav = resolved / "call.wav"
        response_mid = resolved / "response.mid"

        for fname, fpath in (
            ("call.mid", call_mid),
            ("call.wav", call_wav),
            ("response.mid", response_mid),
        ):
            if not fpath.is_file():
                raise IngestError(str(resolved), f"missing {fname}")

        pairs.append(
            PairPath(
                nnn=nnn,
                dir=resolved,
                call_mid=call_mid,
                call_wav=call_wav,
                response_mid=response_mid,
            )
        )

    return pairs

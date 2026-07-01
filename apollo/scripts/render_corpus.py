"""CLI entrypoint: render `call.wav` for every pair from its FM manifest.

Usage:
    python -m apollo.scripts.render_corpus <pairs_root> [--tempo-bpm BPM]

For each `<pairs_root>/NNN/` directory that contains a `call_fm.json` + `call.mid`,
renders the call audio via the shared `apollo.synth.render.render_call_wav` and
writes `<pairs_root>/NNN/call.wav` (mono, SR from the spec). `call.wav` is a
DERIVED artifact (reproducible from `call_fm.json` + `call.mid` — the point of
deterministic rendering), so this CLI enumerates pairs by manifest presence
rather than via `apollo.ingest.discover_pairs`, which requires `call.wav` to
already exist (the post-render corpus layout).

Exit codes (mirrors apollo.scripts.ingest_corpus):
    0 — Success; `call.wav` written for every discovered pair.
    1 — `IngestError`: a known per-pair failure (bad manifest / MIDI / cap) with
        the offending pair path in the message. Fix the corpus and re-run.
    2 — Any other exception (bug / environment issue).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import soundfile as sf

from apollo.ingest.errors import IngestError
from apollo.synth.render import render_call_wav
from apollo.synth.spec import SR


def _discover_manifest_pairs(pairs_root: str) -> list[Path]:
    """Return sorted pair directories that have both call_fm.json and call.mid.

    Mirrors the path-traversal safety of apollo.ingest.discover_pairs (T-01-11):
    resolve each entry and verify it stays under the corpus root; skip hidden
    dirs (T-01-16).
    """
    root_path = Path(pairs_root).resolve()
    if not root_path.is_dir():
        raise IngestError(str(root_path), "corpus root not found or not a directory")

    dirs: list[Path] = []
    for entry in sorted(root_path.iterdir(), key=lambda p: p.name):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        resolved = entry.resolve()
        try:
            resolved.relative_to(root_path)
        except ValueError:
            raise IngestError(str(entry), "path traversal: symlink escapes corpus root")
        if (resolved / "call_fm.json").is_file() and (resolved / "call.mid").is_file():
            dirs.append(resolved)
    return dirs


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Render call.wav for every pair from its FM manifest."
    )
    parser.add_argument("pairs_root", help="Path to the data/pairs/ directory")
    parser.add_argument(
        "--tempo-bpm",
        type=float,
        default=120.0,
        help="Corpus tempo in bpm (default: 120.0; must match authored corpus)",
    )
    args = parser.parse_args(argv)

    try:
        pair_dirs = _discover_manifest_pairs(args.pairs_root)
        n = 0
        for pair_dir in pair_dirs:
            manifest_path = str(pair_dir / "call_fm.json")
            mid_path = str(pair_dir / "call.mid")
            audio = render_call_wav(
                manifest_path,
                mid_path,
                pair_path=str(pair_dir),
                call_bpm=args.tempo_bpm,
            )
            sf.write(str(pair_dir / "call.wav"), audio, SR)
            n += 1
        print(f"OK: rendered {n} call.wav -> {args.pairs_root}")
        return 0
    except IngestError as e:
        print(f"RENDER FAILED: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"UNEXPECTED ERROR: {e!r}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

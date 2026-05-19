"""CLI entrypoint: build the Apollo tokenized corpus artifact.

Usage:
    python -m apollo.scripts.ingest_corpus <pairs_root> [--output PATH] [--tempo-bpm BPM]

Exit codes (RESEARCH.md §"Error Handling / Top-level CLI behavior"):
    0 — Success; artifact written to `--output`.
    1 — `IngestError`: a known per-pair failure with the offending pair path
        in the message. Fix the corpus and re-run.
    2 — Any other exception (bug / environment issue).

Default `--output` is `artifacts/tokenized_v1.pt` (Open Risks #9).
"""

from __future__ import annotations

import argparse
import sys

from apollo.ingest import IngestError, ingest, save_artifact


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the Apollo tokenized corpus artifact."
    )
    parser.add_argument(
        "pairs_root", help="Path to the data/pairs/ directory"
    )
    parser.add_argument(
        "--output",
        default="artifacts/tokenized_v1.pt",
        help="Output .pt artifact path (default: artifacts/tokenized_v1.pt)",
    )
    parser.add_argument(
        "--tempo-bpm",
        type=float,
        default=120.0,
        help="Corpus tempo in bpm (default: 120.0; must match authored corpus)",
    )
    args = parser.parse_args(argv)

    try:
        artifact = ingest(args.pairs_root, tempo_bpm=args.tempo_bpm)
        save_artifact(artifact, args.output)
        n = artifact["metadata"]["n_pairs"]
        h = artifact["metadata"]["n_heldout"]
        print(f"OK: {n} pairs ({h} heldout) -> {args.output}")
        return 0
    except IngestError as e:
        print(f"INGEST FAILED: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"UNEXPECTED ERROR: {e!r}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

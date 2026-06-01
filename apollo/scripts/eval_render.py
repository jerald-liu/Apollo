"""apollo/scripts/eval_render.py — write runs.jsonl entry + M4L render manifest.

EVAL-03: persists a run-level record per training run.
EVAL-05: surfaces the --iteration flag that marks gate-eligible runs.

Decisions:
- D-08: runs.jsonl is the run-level record store.
- D-09: run_id = compute_run_id(ckpt_bytes, sorted_train_pair_ids).
- D-13: render manifest path = eval/render_manifests/active.json (single source).
- D-16: --iteration sets `iteration: true`; default false (RESEARCH Open Q #4 option a).
        Use only for true corpus-retraining rounds — sweeps/debug runs stay
        iteration: false so the ship-gate banner stays meaningful.

Exit codes:
  0  success — runs.jsonl appended, active.json written, banner printed
  1  known failure (missing checkpoint, missing pairs root, no held-out pairs)
  2  unexpected exception
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

from apollo.eval import (
    DEFAULT_MANIFEST_PATH,
    append_run,
    compute_run_id,
    enumerate_heldout,
    write_render_manifest,
)
from apollo.ingest.pairs import discover_pairs
from apollo.ingest.split import is_heldout


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _derive_train_pair_ids(pairs_root: str) -> list[str]:
    """All non-held-out pair NNNs, sorted ascending."""
    return sorted(p.nnn for p in discover_pairs(pairs_root) if not is_heldout(p.nnn))


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=False, timeout=2,
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="eval_render",
        description="Compute run_id, append runs.jsonl, write M4L render manifest.",
    )
    parser.add_argument("checkpoint", help="path to .pt checkpoint")
    parser.add_argument("--pairs-root", default="data/pairs",
                        help="corpus root (default: data/pairs)")
    parser.add_argument("--iteration", action="store_true",
                        help="mark this run as iteration:true in runs.jsonl (D-16). "
                             "Use only for true corpus-retraining rounds.")
    parser.add_argument("--iteration-label", default="",
                        help="optional human label, e.g. 'iter-02'")
    parser.add_argument("--notes", default="",
                        help="freeform user notes for this run")
    parser.add_argument("--runs-path", default="eval/runs.jsonl")
    parser.add_argument("--manifest-path", default=DEFAULT_MANIFEST_PATH)
    args = parser.parse_args(argv)

    try:
        ckpt_path = Path(args.checkpoint)
        if not ckpt_path.is_file():
            print(f"ERROR: checkpoint not found: {ckpt_path}", file=sys.stderr)
            return 1

        train_pair_ids = _derive_train_pair_ids(args.pairs_root)
        heldout_pairs = enumerate_heldout(args.pairs_root)
        if not heldout_pairs:
            print(
                f"ERROR: no held-out pairs under {args.pairs_root!r}. "
                f"Phase 1's hash split needs >=1 pair where is_heldout(nnn) is true.",
                file=sys.stderr,
            )
            return 1

        run_id = compute_run_id(str(ckpt_path), train_pair_ids)
        record = {
            "run_id": run_id,
            "checkpoint_path": str(ckpt_path),
            "checkpoint_hash": _sha256_file(ckpt_path),
            "train_pair_ids": train_pair_ids,
            "n_train_pairs": len(train_pair_ids),
            "n_heldout_pairs": len(heldout_pairs),
            "iteration": bool(args.iteration),
            "iteration_label": args.iteration_label,
            "git_sha": _git_sha(),
            "notes": args.notes,
        }
        append_run(record, path=args.runs_path)
        manifest_out = write_render_manifest(
            run_id, args.pairs_root, manifest_path=args.manifest_path
        )

        print(
            f"OK: run_id={run_id} "
            f"iteration={'true' if args.iteration else 'false'} "
            f"heldout={len(heldout_pairs)} "
            f"manifest={manifest_out}"
        )
        return 0
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"UNEXPECTED ERROR: {e!r}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

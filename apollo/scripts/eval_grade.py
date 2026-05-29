"""CLI launcher for the Phase-4 Flask grading UI (EVAL-02, D-04).

Usage:
    python -m apollo.scripts.eval_grade <pairs_root> --run-id <id> [--port 5000]
        [--runs-path eval/runs.jsonl] [--scores-path eval/scores.jsonl]

Binds 127.0.0.1 only (RESEARCH §Anti-Patterns — never expose the grading UI on a
public interface). Uses Flask's development server; this is a single-user local
tool, not a production deployment.
"""
from __future__ import annotations

import argparse
import sys
from typing import Sequence

from apollo.eval.web.app import _find_run_record, create_app


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="apollo.scripts.eval_grade",
        description="Launch the Apollo grading UI on 127.0.0.1.",
    )
    p.add_argument("pairs_root", help="Path to data/pairs/ root.")
    p.add_argument("--run-id", required=True, help="Run identifier to grade.")
    p.add_argument("--port", type=int, default=5000, help="TCP port (default: 5000).")
    p.add_argument("--runs-path", default="eval/runs.jsonl")
    p.add_argument("--scores-path", default="eval/scores.jsonl")
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    # Validate run_id exists in runs.jsonl before launching — a typo silently
    # makes /reveal return all-None and a grader could score for ten pairs
    # before noticing the metadata is empty (WR-02).
    if _find_run_record(args.run_id, args.runs_path) is None:
        print(
            f"WARN: run_id={args.run_id!r} not found in {args.runs_path} — "
            f"/reveal will return null metadata. Did you forget to run eval_render?",
            file=sys.stderr,
        )
    print(
        f"Apollo grading UI: http://127.0.0.1:{args.port}/  run_id={args.run_id[:8]}",
        file=sys.stderr,
    )
    app = create_app(
        pairs_root=args.pairs_root,
        run_id=args.run_id,
        runs_path=args.runs_path,
        scores_path=args.scores_path,
    )
    # 127.0.0.1 binding is non-negotiable (RESEARCH §Anti-Patterns).
    app.run(host="127.0.0.1", port=args.port, debug=False)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

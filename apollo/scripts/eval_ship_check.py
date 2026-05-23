"""apollo/scripts/eval_ship_check.py — ship-gate decision as exit code.

EVAL-05: returns 0 if the last two iteration-marked runs both improved over
their predecessor rows in runs.jsonl; non-zero otherwise.

Decision: D-17 — exit code IS the gate decision. Banner printed to stdout
either way.

Exit codes (NOTE: differs from other scripts — gate decision, not error class):
  0  ship-gate PASS
  1  ship-gate FAIL (insufficient iterations, no improvement, tie, regression,
                    empty data, etc.)
  2  unexpected exception (rare — pure-function over local JSONL)
"""
from __future__ import annotations

import argparse
import sys

from apollo.eval import check_ship_gate


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="eval_ship_check",
        description="Ship-gate decision over eval/runs.jsonl + eval/scores.jsonl (EVAL-05).",
    )
    parser.add_argument("--runs-path", default="eval/runs.jsonl")
    parser.add_argument("--scores-path", default="eval/scores.jsonl")
    args = parser.parse_args(argv)
    try:
        passed, banner = check_ship_gate(args.runs_path, args.scores_path)
        print(banner)
        return 0 if passed else 1
    except Exception as e:
        print(f"UNEXPECTED ERROR: {e!r}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

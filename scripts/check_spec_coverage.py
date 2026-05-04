#!/usr/bin/env python3
"""Check that every spec clause has at least one test referencing its ID.

Extracts clause IDs from specs/*.md (e.g. R5.3, IR→M.1) and verifies a
test function whose name contains the normalised ID exists in tests/**/*.py.

Normalisation: dots and arrows become underscores.
  R5.3    → R_5_3    → matches test_R_5_3_* or test_R5_3_*
  IR→M.1  → IR_M_1   → matches test_IR_M_1_*

Exit 0 if all clauses are covered, 1 otherwise.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SPECS_DIR = ROOT / "specs"
TESTS_DIR = ROOT / "tests"

# Matches **R1.1**, **IR→M.2**, **IS→R.3**, etc.
CLAUSE_RE = re.compile(r"\*\*([A-Z][A-Z0-9]*(?:[→][A-Z]+)?[·.]?[0-9]+\.[0-9]+)\*\*")


def normalise(clause_id: str) -> str:
    """R5.3 → r_5_3,  IR→M.1 → ir_m_1  (lowercase for case-insensitive match)."""
    return re.sub(r"[^a-zA-Z0-9]+", "_", clause_id).strip("_").lower()


def collect_clauses() -> dict[str, str]:
    """Return {clause_id: source_file} for every clause in specs/."""
    clauses: dict[str, str] = {}
    for path in sorted(SPECS_DIR.glob("*.md")):
        if path.name == "README.md":
            continue
        for line in path.read_text().splitlines():
            for m in CLAUSE_RE.finditer(line):
                cid = m.group(1)
                clauses[cid] = path.name
    return clauses


def collect_test_ids() -> set[str]:
    """Return normalised IDs referenced in test function names."""
    ids: set[str] = set()
    for path in TESTS_DIR.rglob("*.py"):
        for line in path.read_text().splitlines():
            for m in re.finditer(r"def (test_[^\s(]+)", line):
                ids.add(m.group(1).lower())
    return ids


def main() -> int:
    clauses = collect_clauses()
    test_ids = collect_test_ids()

    missing = []
    for cid, source in clauses.items():
        needle = normalise(cid)
        if not any(needle in tid for tid in test_ids):
            missing.append((cid, source))

    if missing:
        print("SPEC COVERAGE FAILURE — untested clauses:")
        for cid, source in missing:
            print(f"  {source}: {cid}  (expected test containing '{normalise(cid)}')")
        return 1

    print(f"OK — {len(clauses)} clauses covered.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

---
phase: 04-evaluation-loop
plan: 01
subsystem: eval-scaffold
tags: [scaffold, eval, foundations]
requires: []
provides:
  - "apollo.eval package (importable, empty __all__)"
  - "apollo.eval.web sub-package (importable)"
  - "[project.optional-dependencies] eval extra (flask/pandas/matplotlib/jupyter)"
  - "eval/rubric.md canonical anchor text (D-01..D-03, D-05, D-14, D-16)"
  - "gitignore patterns for eval/scores.jsonl, runs.jsonl, render_manifests/*.json, data/pairs/*/eval/"
affects:
  - "pyproject.toml"
  - ".gitignore"
tech-stack:
  added: [flask, pandas, matplotlib, jupyter]
  patterns:
    - "PEP 621 optional-dependencies extras"
    - "PATTERNS S1: from __future__ import annotations"
key-files:
  created:
    - apollo/eval/__init__.py
    - apollo/eval/web/__init__.py
    - eval/rubric.md
    - eval/render_manifests/.gitkeep
  modified:
    - pyproject.toml
    - .gitignore
decisions: []
metrics:
  duration: "~5 min"
  tasks: 3
  files: 6
  completed: 2026-05-23
requirements_completed: [EVAL-01]
---

# Phase 4 Plan 01: Eval Scaffold Summary

One-liner: Phase-4 foundations — `eval` extra declared, regenerable data gitignored, `apollo.eval{,.web}` packages importable, canonical rubric committed.

## What Was Built

- **`pyproject.toml`:** Added `eval = ["flask>=3.0", "pandas>=2.0", "matplotlib>=3.7", "jupyter>=1.0"]` under `[project.optional-dependencies]`. `pip install -e ".[eval]"` is now the entry point for Phase-4 tooling.
- **`.gitignore`:** New "Phase 4 — eval loop regenerable data" section ignoring `eval/scores.jsonl`, `eval/runs.jsonl`, `eval/render_manifests/*.json`, and `data/pairs/*/eval/`. The `!eval/render_manifests/.gitkeep` negation keeps the placeholder tracked.
- **`apollo/eval/__init__.py`:** Empty `__all__: list[str] = []` placeholder with docstring listing the public surface 04-02 will populate. Cites D-01..D-17.
- **`apollo/eval/web/__init__.py`:** Empty sub-package marker for the Flask UI; `create_app` is 04-04's job.
- **`eval/rubric.md`:** Canonical anchor text for both dimensions (5 anchors each), how-to-grade procedure, free-text note guidance (D-03), iteration marker explanation (D-16), blind-grading note (D-05). Source of truth referenced by UI-SPEC anchor strips.
- **`eval/render_manifests/.gitkeep`:** Empty placeholder so git tracks the directory while transient manifest JSONs stay ignored.

## Commits

- `0a64f3e` chore(04-01): declare eval extra and gitignore regenerable eval data
- `172664b` feat(04-01): scaffold apollo.eval and apollo.eval.web packages
- `909e27e` docs(04-01): add canonical eval/rubric.md and render_manifests/.gitkeep

## Verification

- `python -c "import apollo.eval; import apollo.eval.web"` → exits 0
- `grep 'eval = \["flask>=3.0"' pyproject.toml` → matches
- `git check-ignore eval/rubric.md` → exit 1 (not ignored, correct)
- `git check-ignore eval/render_manifests/.gitkeep` → exit 1 (allow-listed by `!` negation, correct)
- `tomllib.load('pyproject.toml')` → `'flask>=3.0' in eval` extra (validated with python3.11)

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- FOUND: apollo/eval/__init__.py
- FOUND: apollo/eval/web/__init__.py
- FOUND: eval/rubric.md
- FOUND: eval/render_manifests/.gitkeep
- FOUND: commit 0a64f3e
- FOUND: commit 172664b
- FOUND: commit 909e27e

---
phase: 04-evaluation-loop
plan: 03
subsystem: eval-cli-and-notebook
tags: [eval, cli, notebook, ship-gate, render-manifest]
requires:
  - "apollo.eval core surface (04-02)"
  - "apollo.ingest.{pairs,split} (Phase 1)"
provides:
  - "python -m apollo.scripts.eval_render — runs.jsonl writer + M4L manifest writer (EVAL-03)"
  - "python -m apollo.scripts.eval_ship_check — gate decision as exit code (EVAL-05)"
  - "eval/delta.ipynb — per-dim + per-pair trajectories + ship-gate banner (EVAL-04)"
  - "scripts/_bootstrap_delta_notebook.py — regenerable notebook source"
  - "--iteration flag as the explicit gate-eligibility marker (D-16)"
affects:
  - "apollo/scripts/ (two new CLI modules)"
  - "eval/ (delta.ipynb committed)"
  - "scripts/ (new top-level dir for notebook bootstrap)"
tech-stack:
  added: [nbformat]
  patterns:
    - "PATTERNS S1: from __future__ import annotations"
    - "Argparse + exit-code CLI matching apollo/scripts/ convention"
    - "nbformat-as-source for notebooks (deterministic, diffable bootstrap)"
key-files:
  created:
    - apollo/scripts/eval_render.py
    - apollo/scripts/eval_ship_check.py
    - scripts/_bootstrap_delta_notebook.py
    - eval/delta.ipynb
  modified: []
decisions:
  - "eval_render exit codes mirror generate.py/ingest_corpus.py: 0 success, 1 known failure (missing ckpt / no held-out), 2 unexpected. Auth/file errors are 1 not 2."
  - "eval_ship_check exit code carries the gate decision (0=PASS, 1=FAIL, 2=unexpected). Distinct semantics from other scripts — documented in module docstring."
  - "checkpoint_hash field uses sha256 (full 64 hex) for byte-level verification while run_id stays blake2b-8 (16 hex) for identity. Distinct hashes, distinct purposes; both are recorded."
  - "Notebook authored via nbformat in a committed bootstrap script (scripts/_bootstrap_delta_notebook.py). Re-running overwrites eval/delta.ipynb with the canonical 5-cell layout. Source-of-truth is the .py script; the .ipynb is regenerable."
  - "Optional bottom-N regressed-pairs cell deliberately omitted to keep canonical layout pinned at 6 cells (1 md + 5 code). Users can append exploratory cells below cell 5."
metrics:
  duration: "~10 min"
  tasks: 3
  files: 4
  completed: 2026-05-23
requirements_completed: [EVAL-04, EVAL-05]
---

# Phase 4 Plan 03: Eval CLI + Delta Notebook Summary

One-liner: Wires the 04-02 pure-function spine to user-facing surfaces — two argparse CLIs (`eval_render`, `eval_ship_check`) plus the canonical `eval/delta.ipynb` regenerable from a committed nbformat bootstrap.

## What Was Built

- **`apollo/scripts/eval_render.py`** (~130 LOC) — computes `run_id` via `compute_run_id(ckpt_bytes, sorted_train_pair_ids)`, derives the train set as `discover_pairs - is_heldout`, streams sha256 over the checkpoint for verifiable `checkpoint_hash`, appends one record to `eval/runs.jsonl` (run_id, checkpoint_path, checkpoint_hash, train_pair_ids, n_train_pairs, n_heldout_pairs, iteration, iteration_label, git_sha, notes), and writes the M4L render manifest to `eval/render_manifests/active.json`. `--iteration` is the explicit gate-eligibility flag (D-16); default is `false` so sweeps/debug runs don't pollute the ship-gate banner. Exit codes mirror existing scripts: 0/1/2.
- **`apollo/scripts/eval_ship_check.py`** (~40 LOC) — argparse wrapper around `check_ship_gate`. Exit code carries the gate decision (0 = PASS, 1 = FAIL, 2 = unexpected). `--runs-path` / `--scores-path` let CI / fixtures point at non-default JSONL files.
- **`scripts/_bootstrap_delta_notebook.py`** (~80 LOC) — committed one-shot script using `nbformat.v4` to author `eval/delta.ipynb`. Six cells: markdown header → imports/paths → load+dedup → Plot 1 (per-dim mean across runs) → Plot 2 (per-pair fit trajectory) → ship-gate banner. Underscore-prefixed name signals "internal, not a runtime CLI".
- **`eval/delta.ipynb`** — generated artifact. Valid JSON, 6 cells, all required substrings (`pd.read_json`, `lines=True`, `check_ship_gate`, "Per-dim mean over runs", "Per-pair call-response-fit trajectories"). Cells 1–5 are canonical and pinned in the docstring of the bootstrap.

## Verification

- `python -m apollo.scripts.eval_render --help` lists `--iteration` in usage.
- `python -m apollo.scripts.eval_render does-not-exist.pt` → exit 1 with `ERROR: checkpoint not found` (file-not-found is *known*, not *unexpected* — matches contract).
- `python -m apollo.scripts.eval_ship_check` against the PASS fixture (r1>r0, r3>r2) → exit 0 with `Ship-gate PASS` banner.
- `python -m apollo.scripts.eval_ship_check` against the TIE fixture → exit 1 with `Ship-gate FAIL — improvement not sustained` banner.
- `python scripts/_bootstrap_delta_notebook.py` is idempotent; the resulting notebook has 6 cells and all required substrings in raw JSON.
- `pytest tests/test_run_id.py tests/test_scoring.py tests/test_ship_check.py tests/test_render_manifest.py -x -q` → **31 passed in 0.53s** (no regressions from 04-02).

## Commits

- `5295650` feat(04-03): add eval_render CLI for runs.jsonl + render manifest
- `5f74fbe` feat(04-03): add eval_ship_check CLI wrapper over check_ship_gate
- `f113c8f` feat(04-03): add eval/delta.ipynb + nbformat bootstrap generator

## Deviations from Plan

None — plan executed exactly as written. The CLI bodies, exit-code contracts, render-manifest path, and notebook cell content all match the plan body literally. The TIE-fixture FAIL banner reads `Ship-gate FAIL — improvement not sustained:` (set by `check_ship_gate` from 04-02), which is what the verify-block expected (non-zero exit + banner present).

## Self-Check: PASSED

- FOUND: apollo/scripts/eval_render.py
- FOUND: apollo/scripts/eval_ship_check.py
- FOUND: scripts/_bootstrap_delta_notebook.py
- FOUND: eval/delta.ipynb
- FOUND: commit 5295650
- FOUND: commit 5f74fbe
- FOUND: commit f113c8f

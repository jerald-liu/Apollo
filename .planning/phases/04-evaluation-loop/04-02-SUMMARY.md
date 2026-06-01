---
phase: 04-evaluation-loop
plan: 02
subsystem: eval-core
tags: [eval, pure-functions, jsonl, ship-gate, tdd]
requires:
  - "apollo.eval package (04-01)"
  - "apollo.ingest.{pairs,split,mock} (Phase 1)"
provides:
  - "apollo.eval.compute_run_id (blake2b-8 over checkpoint + sorted pair-ids)"
  - "apollo.eval.enumerate_heldout (heldout subset wrapper)"
  - "apollo.eval.append_score / append_score_pair / load_scores (JSONL store)"
  - "apollo.eval.append_run (runs.jsonl writer with auto-created stamp)"
  - "apollo.eval.check_ship_gate (D-14..D-17 pure decision)"
  - "apollo.eval.write_render_manifest (M4L active.json writer)"
  - "apollo.eval.DEFAULT_MANIFEST_PATH constant"
affects:
  - "apollo/eval/__init__.py (now re-exports the full Phase-4 core surface)"
tech-stack:
  added: []
  patterns:
    - "PATTERNS S1: from __future__ import annotations on every module"
    - "Append-only JSONL (D-08)"
    - "Single-open() atomicity for paired score writes (RESEARCH Pitfall 2)"
    - "Last-write-wins reducer on (run_id, pair_id, dim)"
    - "blake2b digest_size=8 → 16-hex run_id (RESEARCH Pattern 2)"
key-files:
  created:
    - apollo/eval/heldout.py
    - apollo/eval/run_id.py
    - apollo/eval/runs_log.py
    - apollo/eval/scores_log.py
    - apollo/eval/ship_check.py
    - apollo/eval/render_manifest.py
    - tests/test_run_id.py
    - tests/test_scoring.py
    - tests/test_ship_check.py
    - tests/test_render_manifest.py
  modified:
    - apollo/eval/__init__.py
decisions:
  - "Ship-gate predecessor = immediately previous row in runs.jsonl (A2 literal reading), may be a non-iteration run. Alternative reading documented in plan assumptions block — flip is a one-line change if user disagrees."
  - "append_score_pair writes fit + coherence from a single open() call to enforce paired-submit atomicity per RESEARCH Pitfall 2."
  - "Ship-gate tie (Δ=0) is FAIL, not PASS — strict `>` per D-14 'up by any ε'."
  - "Coherence ignored by ship-gate; only fit gates ship (D-14). Coherence still logged for delta.ipynb."
  - "Render manifest contains ONE entry per held-out pair, always `response_001.mid`. N-sample grading deferred to v2."
metrics:
  duration: "~15 min"
  tasks: 4
  files: 10
  tests: 31
  completed: 2026-05-23
requirements_completed: [EVAL-03, EVAL-05]
---

# Phase 4 Plan 02: Eval Core Summary

One-liner: CI-coverable pure-function spine of Phase 4 — run-id hashing, JSONL score/run store, ship-gate decision, M4L render manifest. 6 modules, 4 test files, 31 green tests under TDD discipline.

## What Was Built

- **`apollo/eval/heldout.py`** — `enumerate_heldout(pairs_root)` composes `discover_pairs` (Phase 1) with `is_heldout` (DATA-04) to produce the deterministic held-out subset. ~20 LOC.
- **`apollo/eval/run_id.py`** — `compute_run_id(ckpt, pair_ids)` returns a 16-char blake2b-8 hex over `checkpoint_bytes + b"\x00CORPUS\x00" + sorted(pair_ids)`. Streamed in 64 KiB chunks. Deterministic across platforms, invariant to caller's pair-id ordering. Test `test_run_id_matches_literal_formula` pins the byte stream — changing it would invalidate every existing `runs.jsonl` entry.
- **`apollo/eval/scores_log.py`** — `append_score` and `append_score_pair` both write JSON lines into `eval/scores.jsonl` with `(run_id, pair_id, dim, score, note, ts)`. `append_score_pair` issues both lines from a single `open("a")` call so a crash mid-pair leaves either zero records or both (RESEARCH Pitfall 2). `load_scores(run_id=...)` filters by run; returns `[]` if file missing (Pitfall 7). `_VALID_DIMS = {"fit","coherence"}` and `1 <= score <= 5` are asserted.
- **`apollo/eval/runs_log.py`** — `append_run(record)` writes one JSONL record to `eval/runs.jsonl`. Auto-fills `created` with ISO-UTC `isoformat(timespec="seconds")` if absent. Copies caller's dict before mutating (verified by `test_runs_log_does_not_mutate_caller_record`).
- **`apollo/eval/ship_check.py`** — `check_ship_gate(runs_path, scores_path) -> (bool, str)`. Reduces scores via last-write-wins per `(run_id, pair_id, dim)`, computes `mean(fit)` per run, compares each of the last two iteration-marked runs against the immediately-preceding row. Returns banner with `Δ mean fit = +0.000` formatting. Strict `>` enforces D-14 "up by any ε". Eight failure branches covered by tests: empty/missing data, <2 iteration runs, missing predecessor (idx 0), tie, regression, no-fit-recorded, plus PASS and last-write-wins paths.
- **`apollo/eval/render_manifest.py`** — `write_render_manifest(run_id, pairs_root)` writes `{"run_id", "entries": [{"nnn", "response_mid", "out_wav", "notes_json"}, ...]}` to `eval/render_manifests/active.json` (D-13 single-source path). Held-out pairs without `response_001.mid` are skipped with a stderr warning so the user knows to re-run `generate.py`.
- **`apollo/eval/__init__.py`** — Replaced 04-01 placeholder with the full re-export surface: `enumerate_heldout`, `compute_run_id`, `append_run`, `append_score`, `append_score_pair`, `load_scores`, `check_ship_gate`, `write_render_manifest`, `DEFAULT_MANIFEST_PATH`.

## Test Coverage

| File                                | Tests | Notes                                                  |
| ----------------------------------- | ----- | ------------------------------------------------------ |
| tests/test_run_id.py                | 6     | Determinism, sort-invariance, literal-formula pin      |
| tests/test_scoring.py               | 11    | JSONL round-trip, atomicity, filter, empty, mutate     |
| tests/test_ship_check.py            | 9     | Empty / 1-iter / pass / tie / regress / non-iter pred / coherence-ignored / last-write-wins |
| tests/test_render_manifest.py       | 5     | Heldout-only, skip-missing, schema pin, mkdir, re-exports |

`pytest tests/test_run_id.py tests/test_scoring.py tests/test_ship_check.py tests/test_render_manifest.py -x -q` → **31 passed in 0.56s**.

## Commits

TDD pairs (test → feat) per task:

- `c4da76b` test(04-02): add failing tests for compute_run_id determinism
- `dff922f` feat(04-02): implement compute_run_id and enumerate_heldout
- `9d1c233` test(04-02): add failing tests for scores_log and runs_log
- `45a1fde` feat(04-02): implement scores_log and runs_log JSONL append surface
- `d8bc8b1` test(04-02): add failing tests for check_ship_gate
- `0a34f3d` feat(04-02): implement check_ship_gate over runs.jsonl + scores.jsonl
- `68f3528` test(04-02): add failing tests for write_render_manifest
- `eaf93ac` feat(04-02): implement write_render_manifest and populate apollo.eval re-exports

## Verification

- `pytest tests/test_run_id.py tests/test_scoring.py tests/test_ship_check.py tests/test_render_manifest.py -x -q` → 31 passed
- `python -c "from apollo.eval import compute_run_id, enumerate_heldout, append_run, append_score, append_score_pair, load_scores, check_ship_gate, write_render_manifest; print('ok')"` → exits 0
- All modules carry `from __future__ import annotations` and cite their D-numbers in docstrings.
- `grep -q "DEFAULT_MANIFEST_PATH = \"eval/render_manifests/active.json\"" apollo/eval/render_manifest.py` → match
- `grep -q "all(d > 0" apollo/eval/ship_check.py` → match (strict `>`, not `>=`)
- `grep -q "blake2b(digest_size=8)" apollo/eval/run_id.py` → match

## Deviations from Plan

None — plan executed exactly as written. Every test from the plan body was lifted verbatim; the ship-gate banner formatting matches the specified `Δ mean fit = {d:+.3f}` shape; the FAIL banner shape (not literally spelled out in the plan) lists the same per-pair deltas as the PASS banner under a "Ship-gate FAIL — improvement not sustained" header so the message remains informative on tie/regression branches.

## Self-Check: PASSED

- FOUND: apollo/eval/heldout.py
- FOUND: apollo/eval/run_id.py
- FOUND: apollo/eval/runs_log.py
- FOUND: apollo/eval/scores_log.py
- FOUND: apollo/eval/ship_check.py
- FOUND: apollo/eval/render_manifest.py
- FOUND: tests/test_run_id.py
- FOUND: tests/test_scoring.py
- FOUND: tests/test_ship_check.py
- FOUND: tests/test_render_manifest.py
- FOUND: commit c4da76b
- FOUND: commit dff922f
- FOUND: commit 9d1c233
- FOUND: commit 45a1fde
- FOUND: commit d8bc8b1
- FOUND: commit 0a34f3d
- FOUND: commit 68f3528
- FOUND: commit eaf93ac

## TDD Gate Compliance

Each of the 4 tasks landed as a `test(...)` commit (RED) followed by a `feat(...)` commit (GREEN). No REFACTOR commits — the green implementations were already minimal and clean, no behavior-preserving cleanup was warranted.

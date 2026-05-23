---
status: testing
phase: 04-evaluation-loop
source:
  - .planning/phases/04-evaluation-loop/04-01-SUMMARY.md
  - .planning/phases/04-evaluation-loop/04-02-SUMMARY.md
  - .planning/phases/04-evaluation-loop/04-03-SUMMARY.md
  - .planning/phases/04-evaluation-loop/04-04-SUMMARY.md
started: 2026-05-23T14:42:50Z
updated: 2026-05-23T14:42:50Z
---

## Current Test

number: 1
name: Install eval extra
expected: |
  Run `uv pip install -e .[eval]` (or `pip install -e .[eval]`). Installs cleanly with flask, pandas, matplotlib, jupyter. No version conflicts. `python -c "import flask, pandas, matplotlib, jupyter, apollo.eval"` succeeds.
awaiting: user response

## Tests

### 1. Install eval extra
expected: `uv pip install -e .[eval]` installs flask, pandas, matplotlib, jupyter without conflicts. `python -c "import flask, pandas, matplotlib, jupyter, apollo.eval"` succeeds.
result: pending

### 2. Read rubric.md
expected: Open `eval/rubric.md`. Two dimensions clearly defined: "Call-Response Fit (1–5)" and "Musical Coherence (1–5)". Anchor wording for "1 unrelated", "3 listenable", "5 the model gets it". Wording you'd actually use to grade a pair.
result: pending

### 3. Ship-check on empty data
expected: Run `python -m apollo.scripts.eval_ship_check`. With no `eval/runs.jsonl` yet, it exits non-zero and prints a clear message (not a stack trace) — something like "no runs yet" or "ship gate: cannot evaluate".
result: pending

### 4. Cold-start smoke — grading server
expected: From a clean shell with no `eval/scores.jsonl`: `python -m apollo.scripts.eval_grade data/pairs --run-id smoke-test`. Server boots on `127.0.0.1:5000` without errors. Visiting `http://127.0.0.1:5000/` returns a worklist page (may be empty if no held-out pairs yet).
result: pending

### 5. Worklist page
expected: With at least one held-out mock pair present, `GET /` shows the pair NNN with a status badge (· pending, ✓ graded, ⚠ partial). Page title reads "Apollo · Grading". Layout matches UI-SPEC.
result: pending

### 6. Pair page audio + sliders
expected: Click into a pair from the worklist. Audio for `call.wav` plays. Two scoring controls present: "Call-Response Fit (1–5)" and "Musical Coherence (1–5)". Number keys 1–5 set fit; shift+1–5 set coherence. Note field is editable.
result: pending

### 7. Submit a score
expected: Set fit + coherence, optionally add a note, click "Submit & next →" (or press Enter). UI advances to next pair. `eval/scores.jsonl` gains exactly TWO new lines for this pair (one fit record, one coherence record), each with the run_id, pair_id, dim, value, note.
result: pending

### 8. Reveal toggle
expected: On a pair page, the reveal control shows the run_id (and checkpoint path / iteration flag per UI-SPEC). Reveal is hidden by default — you click to see it. Prevents grading bias.
result: pending

### 9. Resumability
expected: After submitting some scores, navigate back to a graded pair. The fit/coherence values and note are pre-filled from the prior record. You can re-submit to overwrite (last-write-wins).
result: pending

### 10. eval_render registers a run
expected: With a Phase 2 checkpoint and at least one held-out mock pair: `python -m apollo.scripts.eval_render <ckpt>` appends one line to `eval/runs.jsonl` with `iteration: false`, and writes `eval/render_manifests/active.json` listing each held-out pair that has `response_001.mid`. `--iteration` flag flips `iteration: true`.
result: pending

### 11. Delta notebook
expected: Open `eval/delta.ipynb` in Jupyter. Cells execute top-to-bottom without errors (works with empty or mock data). Loader cell uses `pd.read_json(..., lines=True)`. Per-dim mean and per-pair trajectory plots render (even if empty).
result: pending

### 12. Ship-gate trips correctly
expected: Author two consecutive `--iteration` runs in runs.jsonl with grading scores that show positive deltas in both fit and coherence. `python -m apollo.scripts.eval_ship_check` exits 0 with a banner. Author a run where the latest delta is zero or negative — exit non-zero.
result: pending

## Summary

total: 12
passed: 0
issues: 0
pending: 12
skipped: 0

## Gaps

[none yet]

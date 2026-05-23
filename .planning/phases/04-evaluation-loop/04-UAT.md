---
status: partial
phase: 04-evaluation-loop
source:
  - .planning/phases/04-evaluation-loop/04-01-SUMMARY.md
  - .planning/phases/04-evaluation-loop/04-02-SUMMARY.md
  - .planning/phases/04-evaluation-loop/04-03-SUMMARY.md
  - .planning/phases/04-evaluation-loop/04-04-SUMMARY.md
started: 2026-05-23T14:42:50Z
updated: 2026-05-23T16:00:00Z
paused: true
resume_with: /gsd-verify-work 4
---

## Current Test

number: 10
name: eval_render registers a run
expected: |
  With a Phase 2 checkpoint and at least one held-out mock pair: `python -m apollo.scripts.eval_render <ckpt>` appends one line to `eval/runs.jsonl` with `iteration: false`, and writes `eval/render_manifests/active.json` listing each held-out pair that has `response_001.mid`. `--iteration` flag flips `iteration: true`.
awaiting: setup — see Resume Notes below
status: paused

## Tests

### 1. Install eval extra
expected: `uv pip install -e .[eval]` installs flask, pandas, matplotlib, jupyter without conflicts. `python -c "import flask, pandas, matplotlib, jupyter, apollo.eval"` succeeds.
result: pass
note: |
  zsh required quoting: `uv pip install -e ".[eval]"`. Verification via
  `uv run python -c "import ... ; print('ok')"` — plain `python` not on PATH
  (macOS python3-only + uv-managed venv).

### 2. Read rubric.md
expected: Open `eval/rubric.md`. Two dimensions clearly defined: "Call-Response Fit (1–5)" and "Musical Coherence (1–5)". Anchor wording for "1 unrelated", "3 listenable", "5 the model gets it". Wording you'd actually use to grade a pair.
result: pass

### 3. Ship-check on empty data
expected: Run `python -m apollo.scripts.eval_ship_check`. With no `eval/runs.jsonl` yet, it exits non-zero and prints a clear message (not a stack trace) — something like "no runs yet" or "ship gate: cannot evaluate".
result: pass
note: |
  Output: "Ship-gate FAIL — no runs recorded; nothing to check." Exit code 1.

### 4. Cold-start smoke — grading server
expected: From a clean shell with no `eval/scores.jsonl`: `python -m apollo.scripts.eval_grade data/pairs --run-id smoke-test`. Server boots on `127.0.0.1:5000` without errors. Visiting `http://127.0.0.1:5000/` returns a worklist page (may be empty if no held-out pairs yet).
result: pass
note: |
  Banner + WR-02 warning printed correctly. Empty-state UI is well-designed —
  shows "No held-out pairs found. Did Phase 3 run? Check data/pairs/ and the
  held-out hash split..." Helpful when corpus is empty.

### 5. Worklist page
expected: With at least one held-out mock pair present, `GET /` shows the pair NNN with a status badge (· pending, ✓ graded, ⚠ partial). Page title reads "Apollo · Grading". Layout matches UI-SPEC.
result: pass
note: |
  All 5 held-out NNNs shown with pending badge, counter "0/5 pairs scored — 5 remaining",
  blind mode active (title: "Apollo · Grading · blind"), deterministic shuffle order
  010, 019, 009, 006, 012.

### 6. Pair page audio + sliders
expected: Click into a pair from the worklist. Audio for `call.wav` plays. Two scoring controls present: "Call-Response Fit (1–5)" and "Musical Coherence (1–5)". Number keys 1–5 set fit; shift+1–5 set coherence. Note field is editable.
result: pass
reported: |
  Initial run failed with 500s on audio routes + shift+number not working.
  Two bugs fixed in commit 99d8af9 on phase-04-fix-grading-ui (PR #17):
  (1) Resolve pairs_root to absolute path — Flask send_file resolves relative
      paths against app.root_path (apollo/eval/web/), not cwd.
  (2) Use e.code (Digit1..Digit5) instead of e.key for digit detection —
      Shift+digit on macOS turns e.key into '!'/'@'/'#'/'$'/'%'.
  Both fixes verified: audio plays, 1..5 sets fit, Shift+1..5 sets coherence,
  note field is editable.
note: Bugs fixed before continuing UAT. Gaps still recorded for traceability.

### 7. Submit a score
expected: Set fit + coherence, optionally add a note, click "Submit & next →" (or press Enter). UI advances to next pair. `eval/scores.jsonl` gains exactly TWO new lines for this pair (one fit record, one coherence record), each with the run_id, pair_id, dim, value, note.
result: pass

### 8. Reveal toggle
expected: On a pair page, the reveal control shows the run_id (and checkpoint path / iteration flag per UI-SPEC). Reveal is hidden by default — you click to see it. Prevents grading bias.
result: pass
note: |
  Cosmetic: \n newlines in reveal text collapse to spaces because .mono CSS
  lacks white-space: pre. Info still readable on one line. Logged below.

### 9. Resumability
expected: After submitting some scores, navigate back to a graded pair. The fit/coherence values and note are pre-filled from the prior record. You can re-submit to overwrite (last-write-wins).
result: pass

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
passed: 9
issues: 1
pending: 2
resolved: 1
skipped: 0

## Resume Notes

**Session paused after test 9/12. Resume with `/gsd-verify-work 4`.**

### What's complete
- Tests 1–9 pass. Two real bugs surfaced and were fixed inline in commit `99d8af9`
  on branch `phase-04-fix-grading-ui` (PR #17):
  - Audio routes 500'd with relative `pairs_root` (Flask `send_file` resolves
    against `app.root_path`, not cwd) → `Path(pairs_root).resolve()` in
    `create_app`. Regression test added.
  - `Shift+1..5` keyboard shortcut for coherence never fired on macOS
    (`e.key` becomes `'!'`/`'@'`/...) → switched to `e.code` (`Digit1..Digit5`).
- One open cosmetic issue (UAT-08): reveal aside `\n` newlines collapse to spaces
  because `.mono` CSS lacks `white-space: pre`. Not blocking; can be a follow-up
  one-line fix in the same PR #17 or its own.

### State on disk (mock UAT fixture)
- `data/pairs/000..019` — 20 mock pairs generated via `apollo.ingest.mock.synthesize_pair`
- Held-out NNNs (5): `006, 009, 010, 012, 019`
- Each held-out pair has `eval/smoke-test/response.wav` (a copy of `call.wav` — UAT tests flow, not audio content)
- `eval/scores.jsonl` has rows for at least pair 010 from test 7 + the re-submit in test 9

### How to resume — tests 10–12 setup

Tests 10, 11, 12 need:
1. A **checkpoint** in `models/` — Phase 2's smoke-train didn't persist one. Run:
   ```bash
   uv run python -m apollo.scripts.train --help    # confirm flags
   uv run python -m apollo.scripts.train --max-steps 4 --out models/smoke.pt
   ```
2. **response_001.mid** in each held-out pair (the manifest writer scans this exact filename per RESEARCH A1). Run:
   ```bash
   uv run python -c "
   from pathlib import Path
   import shutil
   from apollo.ingest.split import is_heldout
   for nnn_dir in sorted(Path('data/pairs').iterdir()):
       if not nnn_dir.is_dir() or not is_heldout(nnn_dir.name):
           continue
       src = nnn_dir / 'response.mid'
       dst = nnn_dir / 'response_001.mid'
       if src.exists() and not dst.exists():
           shutil.copy(src, dst)
   print('done')
   "
   ```

Then:
- **Test 10** — `uv run python -m apollo.scripts.eval_render models/smoke.pt` and `--iteration` variant
- **Test 11** — `uv run jupyter notebook eval/delta.ipynb` and run all cells
- **Test 12** — hand-author two consecutive iteration runs in `runs.jsonl` with positive deltas, then `uv run python -m apollo.scripts.eval_ship_check`

### Cleanup when done
- `rm -rf data/pairs/{000..019}` if you want the mock fixture gone before authoring real corpus
- `rm eval/scores.jsonl eval/runs.jsonl eval/render_manifests/active.json models/smoke.pt`

### Stack context
- Working branch: `phase-04-fix-grading-ui` (PR #17, stacked on #16)
- Last committed: `99d8af9` (UAT-06 fixes)
- One open cosmetic issue (reveal newlines) — fix would be one CSS line

## Gaps

- truth: "Number keys 1–5 set fit; Shift+1–5 set coherence per UI-SPEC §Interaction Contract"
  status: resolved
  reason: "Fixed in 99d8af9 — grade.js now uses e.code (Digit1..Digit5) instead of e.key, which is invariant under Shift on all keyboard layouts."
  severity: major
  test: 6
  resolved_in: phase-04-fix-grading-ui

- truth: "Audio for call.wav plays from the pair page"
  status: resolved
  reason: "Fixed in 99d8af9 — Path(pairs_root).resolve() in create_app. Flask send_file resolves relative paths against the app's root_path (apollo/eval/web/), not cwd. Regression test added (chdir + relative path)."
  severity: major
  test: 6
  resolved_in: phase-04-fix-grading-ui

- truth: "Reveal aside formats run_id/checkpoint/iteration on separate lines (UI-SPEC §Reveal toggle)"
  status: failed
  reason: "Newlines in grade.js textContent collapse to spaces because .mono CSS lacks white-space: pre/pre-wrap. Info is readable but jammed onto one line."
  severity: cosmetic
  test: 8
  artifacts: ["apollo/eval/web/static/style.css (.mono class)"]
  missing: ["white-space: pre-wrap on .mono"]

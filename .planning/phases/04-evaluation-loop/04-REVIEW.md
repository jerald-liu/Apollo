---
phase: 04-evaluation-loop
reviewed: 2026-05-23T00:00:00Z
depth: standard
files_reviewed: 22
files_reviewed_list:
  - apollo/eval/__init__.py
  - apollo/eval/heldout.py
  - apollo/eval/render_manifest.py
  - apollo/eval/run_id.py
  - apollo/eval/runs_log.py
  - apollo/eval/scores_log.py
  - apollo/eval/ship_check.py
  - apollo/eval/web/__init__.py
  - apollo/eval/web/app.py
  - apollo/eval/web/static/grade.js
  - apollo/eval/web/static/style.css
  - apollo/eval/web/templates/index.html
  - apollo/eval/web/templates/pair.html
  - apollo/scripts/eval_grade.py
  - apollo/scripts/eval_render.py
  - apollo/scripts/eval_ship_check.py
  - scripts/_bootstrap_delta_notebook.py
  - tests/test_eval_web.py
  - tests/test_render_manifest.py
  - tests/test_run_id.py
  - tests/test_scoring.py
  - tests/test_ship_check.py
  - pyproject.toml
findings:
  critical: 0
  warning: 4
  info: 6
  total: 10
status: issues_found
---

# Phase 4: Code Review Report

**Reviewed:** 2026-05-23
**Depth:** standard
**Files Reviewed:** 22
**Status:** issues_found

## Summary

Phase 4 ships the evaluation loop cleanly. Security posture is solid: Flask binds 127.0.0.1 with `debug=False`, every `<nnn>` route variable is validated against `enumerate_heldout()` set membership before any Path construction (the path-traversal test confirms this works), no `eval`/`exec`/`shell=True` anywhere, hashing is deterministic and well-pinned by tests, and there is no pickle/`weights_only` surface in this phase (no `torch.load` calls). The subprocess call to `git rev-parse` uses a list argv with `timeout=2` and `check=False` — safe. JSONL writes are append-only with `flush()`, and `append_score_pair` correctly batches both lines through a single `open()` to honor RESEARCH Pitfall 2.

The findings below are mostly correctness/robustness concerns. The most important is the use of Python's built-in `hash()` for the deterministic shuffle seed — `hash()` of strings is randomized per-process by PYTHONHASHSEED, so the "deterministic per-run" shuffle is only deterministic within a single Flask process. Restarting `eval_grade` re-shuffles the worklist, which can disorient a grader resuming a session.

Test coverage is good and uses real filesystem I/O (`tmp_path`, `synthesize_pair`) rather than mocks. The path-traversal smoke test is the right shape. Concurrency for JSONL writes is not tested but is also not a real concern for a single-user local tool (single grader, single process).

## Warnings

### WR-01: `hash(run_id)` shuffle seed is non-deterministic across processes

**File:** `apollo/eval/web/app.py:41`
**Issue:** `random.Random(hash(run_id))` seeds with Python's built-in `hash()`. For strings, `hash()` is salted per-process via `PYTHONHASHSEED` (random by default since Python 3.3). The worklist order therefore changes every time `eval_grade` is restarted, undermining UI-SPEC §Blind Grading's "deterministic shuffle per run" claim and the resumability story (a grader resuming after lunch sees a different order; "next pending" still works but the visual worklist re-orders under them).
**Fix:**
```python
import hashlib
def _shuffled_pair_nnns(pairs_root: str, run_id: str) -> List[str]:
    nnns = [p.nnn for p in enumerate_heldout(pairs_root)]
    seed = int.from_bytes(hashlib.blake2b(run_id.encode(), digest_size=8).digest(), "big")
    rng = random.Random(seed)
    rng.shuffle(nnns)
    return nnns
```

### WR-02: `eval_grade.py` does not surface UI URL or run banner on startup

**File:** `apollo/scripts/eval_grade.py:42`
**Issue:** `app.run(host="127.0.0.1", port=args.port, debug=False)` blocks immediately. Flask prints its own banner, but there is no Apollo-side log of "grading run X at http://127.0.0.1:5000/" — and crucially no warning if `run_id` does not appear in `runs.jsonl` (the `/reveal` endpoint will return all-None metadata silently). A grader could be scoring a typo'd `run_id` for ten pairs before noticing. This is a minor robustness gap, not a security issue.
**Fix:** Before `app.run(...)`, check `_find_run_record(run_id, runs_path)` and print a warning to stderr if missing; print `f"Apollo grading UI: http://127.0.0.1:{args.port}/  run_id={run_id[:8]}"`.

### WR-03: `_find_run_record` silently swallows malformed JSONL lines

**File:** `apollo/eval/web/app.py:57-70`, `apollo/eval/ship_check.py:31-40`, `apollo/eval/scores_log.py:74-75`
**Issue:** All three JSONL readers call `json.loads(line)` without try/except. A single corrupted line (e.g. partial write after `kill -9`) raises `JSONDecodeError` and brings down the gate / UI / reveal endpoint. For the ship-gate this is arguably the desired loud failure, but for `/reveal` and `/score/<nnn>` it means a single bad line takes down the whole grading session. Not flagged Critical because POSIX append atomicity makes partial lines unlikely on local disk, but worth noting.
**Fix:** In `app.py` `_find_run_record` and `load_scores`, wrap `json.loads(line)` in a try/except that logs to stderr and skips the line. Keep the ship-gate strict.

### WR-04: `submit_score` next-pair computation re-reads scores file every POST

**File:** `apollo/eval/web/app.py:163-165`
**Issue:** After `append_score_pair`, the handler calls `_graded_pair_ids` which re-reads the entire `scores.jsonl`. For a 30-pair held-out set with two dim records per submit this is fine, but the function shape invites a TOCTOU window — between the append (line 158) and the re-read (line 164), a concurrent write could change "next pending". For v1 single-grader use this is not exploitable. Out of scope per Phase 4 single-user assumption, but document it.
**Fix:** Acceptable for v1; add a comment noting "single-grader assumption — no locking" near the read.

## Info

### IN-01: `enumerate_heldout` re-walks the filesystem on every request

**File:** `apollo/eval/web/app.py:87-92, 96, 117, 163`
**Issue:** Each request calls `_heldout_set()` or `_shuffled_pair_nnns()`, which invokes `enumerate_heldout(pairs_root)` and thus `discover_pairs`. For a single grader on local disk this is cheap; flagging because v1 is explicit about not optimizing. No action required.
**Fix:** None for v1. If perf becomes an issue, cache on `app.config["HELDOUT_NNNS"]` at startup — but then `data/pairs/` mutations during a session won't be picked up. Current behavior is correct.

### IN-02: `random.Random` for shuffle seed — non-cryptographic intentional

**File:** `apollo/eval/web/app.py:41`
**Issue:** `random.Random` is the right primitive here (deterministic seeding), not a security weakness. Noted for completeness in case a linter flags `random` in a web context.
**Fix:** None. Add `# noqa` or a comment if a future linter complains.

### IN-03: `int(data["fit"])` accepts floats / booleans silently

**File:** `apollo/eval/web/app.py:149-150`
**Issue:** `int(3.7)` → 3, `int(True)` → 1. A buggy client posting `{"fit": 3.7}` gets silently truncated to 3 instead of a 400. The 1..5 range check still catches obviously bad input. Minor.
**Fix:**
```python
if not isinstance(data.get("fit"), int) or isinstance(data.get("fit"), bool):
    return jsonify({"ok": False, "error": "fit must be int"}), 400
```

### IN-04: `pretty_midi` not in `eval` extras even though manifest writer documents `.notes.json` sidecars

**File:** `pyproject.toml:18-20`
**Issue:** Not strictly a bug — `render_manifest.py` doesn't parse MIDI, it only records paths. The notes-JSON sidecar is the M4L preprocessing step's responsibility per the module docstring. Just flagging that anyone reading the manifest module may expect a MIDI dep.
**Fix:** None — current design is correct.

### IN-05: `scripts/_bootstrap_delta_notebook.py` uses `pd.DataFrame.iteration.sum()` on possibly-missing column

**File:** `scripts/_bootstrap_delta_notebook.py:45-46`
**Issue:** The cell guards with `if 'iteration' in runs else 0`. Correct. But the f-string nesting (`{runs['iteration'].sum() if 'iteration' in runs else 0}`) is hard to read. Style only.
**Fix:** Pre-compute `n_iter = runs['iteration'].sum() if 'iteration' in runs else 0` on a separate line.

### IN-06: `revealAside.textContent` interpolation uses run_id directly

**File:** `apollo/eval/web/static/grade.js:102-105`
**Issue:** `textContent` (not `innerHTML`) is XSS-safe — no escape needed. Confirming this is intentional and correct, not a bug. Listed as Info to head off a future "should this be sanitized?" question.
**Fix:** None.

---

_Reviewed: 2026-05-23_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

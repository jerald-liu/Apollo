---
phase: 04-evaluation-loop
plan: 04
subsystem: eval-web
tags: [eval, flask, ui, grading, web]
requires:
  - "apollo.eval.{heldout,scores_log} (04-02)"
  - "apollo.ingest.synthesize_pair (Phase 1)"
provides:
  - "apollo.eval.web.app.create_app — Flask grading UI factory"
  - "apollo.scripts.eval_grade — CLI launcher (127.0.0.1)"
  - "Templates: index.html (worklist) + pair.html (score one pair)"
  - "Static assets: style.css (functional palette) + grade.js (interactions)"
affects:
  - "apollo/eval/web/ (new app.py + templates/ + static/)"
  - "apollo/scripts/ (new eval_grade.py)"
  - "tests/ (new test_eval_web.py — 13 Flask test_client smokes)"
tech-stack:
  added: []
  patterns:
    - "PATTERNS S1: from __future__ import annotations"
    - "PATTERNS S4: set-membership validation before path construction (path traversal)"
    - "RESEARCH Pattern 3: create_app factory + app.config DI"
    - "RESEARCH Pitfall 2: single-open atomic paired write via append_score_pair"
    - "UI-SPEC §Copywriting Contract: locked strings verbatim"
key-files:
  created:
    - apollo/eval/web/app.py
    - apollo/eval/web/templates/index.html
    - apollo/eval/web/templates/pair.html
    - apollo/eval/web/static/style.css
    - apollo/eval/web/static/grade.js
    - apollo/scripts/eval_grade.py
    - tests/test_eval_web.py
  modified: []
decisions:
  - "Stub Task 3 (CLI launcher) authored from frontmatter artifacts spec + must-have truth — the PLAN file is truncated mid-Task-2 verify block; no Task 3 <task> block exists. The launcher implements the documented contract: `python -m apollo.scripts.eval_grade <pairs_root> --run-id <id>` binds 127.0.0.1:5000 via `app.run`."
  - "Templates created alongside Task 1's app.py (not deferred to Task 2) because render_template requires templates to exist before any route returning HTML can be tested. Static assets (style.css, grade.js) remained the pure Task 2 deliverable."
metrics:
  duration: "~10 min"
  tasks: 3
  files: 7
  tests: 13
  completed: 2026-05-23
requirements_completed: [EVAL-02]
---

# Phase 4 Plan 04: Grading UI Summary

One-liner: Flask grading UI (5 user routes + 2 helpers, 2 Jinja templates, vanilla CSS/JS) bound to 127.0.0.1 — implements EVAL-02 blind-resumable scoring against the UI-SPEC copywriting + interaction contract.

## What Was Built

- **`apollo/eval/web/app.py`** — `create_app(pairs_root, run_id, runs_path?, scores_path?)` returns a Flask app with seven routes:
  - `GET /` — deterministically-shuffled worklist (`random.Random(hash(run_id))`), with `graded` (last-write-wins on `(pair_id, dim)` requiring both `fit` AND `coherence`) and `unrenderable` (missing `eval/<run_id>/response.wav`) sets passed to `index.html`.
  - `GET /pair/<nnn>` — validates nnn against `enumerate_heldout` membership before any Path construction (PATTERNS S4), renders `pair.html` with `position`/`total`.
  - `GET /audio/<nnn>/call.wav` — `send_file(audio/wav)`; 404 on unknown nnn or missing file.
  - `GET /audio/<nnn>/response.wav` — serves `<pairs_root>/<nnn>/eval/<run_id>/response.wav` (D-13).
  - `POST /score` — JSON `{pair_id, fit, coherence, note}`; rejects out-of-range (400) and unknown pair (404); writes both dims via `append_score_pair` (single-open atomicity, RESEARCH Pitfall 2); returns `{ok: true, next: <next_pending_nnn>}` for client auto-advance.
  - `GET /reveal/<nnn>` — reads runs.jsonl fresh per call, returns `{run_id, checkpoint_path, iteration}` (D-05 blind reveal).
  - `GET /score/<nnn>` — pre-population helper for resumability (UI-SPEC §Resumability); returns `{fit, coherence, note}` or all-null defaults.
- **`apollo/eval/web/templates/index.html`** — Worklist view per UI-SPEC §Layout/GET-/. Three pair-state rendering branches: pending (`·` glyph, "Score →" link), done (`✓` accent glyph, "Re-score" secondary), unrenderable (`⚠` destructive, "no response — re-render" muted, no link). Done banner + empty-state copy match UI-SPEC §Copywriting Contract verbatim.
- **`apollo/eval/web/templates/pair.html`** — Score-one-pair view. Two `<audio controls preload="auto">` players + "▶ Play call → response" sequence button. Two segmented score controls (1–5 buttons, `data-dim="fit"|"coherence"`) with collapsed anchor strips. Optional note textarea. Footer: "← back to worklist", "Submit & next →" (disabled until both scores set), "🔎 reveal" link. `<details>` block lists the 7 keyboard shortcuts. All copy strings match UI-SPEC §Copywriting Contract.
- **`apollo/eval/web/static/style.css`** — `:root` custom properties for the 60/30/10 functional palette (`#FAFAFA`/`#1A1A1A`/`#F0F0F0`/`#666666`/`#0066CC`/`#CC3333`), 4-tier spacing scale (xs/sm/md/lg/xl), 3 typography roles (body 16/400/1.5, label 14/500/1.4, heading 20/600/1.3). 40×40 score buttons, single 80ms transition on `background`. Monospace fallback for the reveal aside (13px). No external imports.
- **`apollo/eval/web/static/grade.js`** — IIFE wired off `document.body.dataset.nnn`. Score-button click → `setScore` (toggles `.selected`, gates Submit). Audio sequence: pause + seek both, play call, on `ended` play response, restore button label on response `ended`. Submit posts JSON, follows `data.next` on success, or shows the locked error string from UI-SPEC §Copywriting Contract. Reveal injects `run_id/checkpoint/iteration` into the aside in monospace. Keyboard: `Space` / `r` (replay) / `1–5` (fit) / `Shift+1–5` (coherence) / `n` (focus note) / `Enter` (submit) / `Esc` (blur note). Resumability: fetches `/score/<nnn>` at load to pre-fill prior scores + note.
- **`apollo/scripts/eval_grade.py`** — CLI launcher: `python -m apollo.scripts.eval_grade <pairs_root> --run-id <id> [--port 5000]`. Binds 127.0.0.1 only (RESEARCH §Anti-Patterns). `--runs-path` / `--scores-path` are CLI-overridable for testing parity.
- **`tests/test_eval_web.py`** — 13 Flask `test_client` smokes covering: worklist render, pair page (valid + unknown + path-traversal-as-nnn), audio routes (success + missing response + path-traversal), `POST /score` (atomic two-line write + unknown-pair 404 + out-of-range 400), `/reveal` (returns seeded run record), `/score/<nnn>` (pre-pop after submit + nulls for ungraded). Fixture synthesizes 10 mock pairs via `synthesize_pair` and seeds a one-row `runs.jsonl`.

## Commits

- `e0ab02e` test(04-04): add failing tests for Flask grading UI
- `f12380d` feat(04-04): implement Flask grading UI app and templates
- `c927dbe` feat(04-04): add grading UI static assets (style.css, grade.js)
- `96e833e` feat(04-04): add eval_grade CLI launcher binding 127.0.0.1

## Verification

- `pytest tests/test_eval_web.py -x -q` → **13 passed in 0.67s**
- `python -c "from apollo.eval.web.app import create_app; print(create_app)"` → exits 0
- `python -c "from apollo.scripts.eval_grade import main, _parse_args; print(_parse_args(['data/pairs','--run-id','abc']).port)"` → `5000`
- `grep -q "append_score_pair" apollo/eval/web/app.py` → match
- `grep -q "_validate_nnn" apollo/eval/web/app.py` → match (membership check before Path construction)
- `grep -q "127.0.0.1" apollo/scripts/eval_grade.py` → match (binding lives in the CLI, not the app factory)
- UI-SPEC §Copywriting Contract locked strings present verbatim: "Apollo · Grading", "Call-Response Fit (1–5)", "Musical Coherence (1–5)", "Submit & next →", "🔎 reveal", "Set both scores to enable submit.", "1 unrelated · 3 plausible · 5 exactly what I'd play", "1 wrong notes · 3 coherent statement · 5 could ship as-is", "Note (optional)", error-on-save string in `grade.js`. All verified by grep.
- `#0066CC` accent color present in style.css (UI-SPEC §Color contract).

## Deviations from Plan

**1. [Rule 3 - Blocking] Added pytest to the venv via `uv pip install pytest`.**
- **Found during:** Task 1 RED phase — `pytest` was not installed in `.venv/`.
- **Issue:** All prior plans' tests were written but the worktree's venv lacked the `pytest` executable.
- **Fix:** `uv pip install pytest` (resolved pytest 9.0.3, iniconfig, pluggy).
- **Impact:** No production code touched; tooling install only.

**2. [Rule 3 - Blocking] Created Jinja templates during Task 1 (not Task 2).**
- **Found during:** Task 1 GREEN phase.
- **Issue:** `render_template` in app.py routes requires templates to exist before any HTML-returning route can be tested with `test_client`. Strict Task-1-only execution (app.py + tests) would have left 13 tests red.
- **Fix:** Created `index.html` + `pair.html` alongside `app.py` in the Task 1 commit. Task 2's static assets (`style.css`, `grade.js`) were committed separately.
- **Files modified:** `apollo/eval/web/templates/{index,pair}.html` moved from Task-2 commit into Task-1 commit.

**3. [Rule 2 - Missing critical functionality] Stub-authored Task 3 from the frontmatter spec.**
- **Found during:** Reading the plan file.
- **Issue:** The PLAN.md file is truncated at line 854 inside Task 2's `<verify>` block — there is no `<task>` block for Task 3 (`apollo/scripts/eval_grade.py`), even though it is listed in `frontmatter.must_haves.artifacts` and required by the must-have truth `python -m apollo.scripts.eval_grade data/pairs --run-id <id> starts the server on 127.0.0.1:5000`.
- **Fix:** Implemented `apollo/scripts/eval_grade.py` to satisfy the documented contract: argparse with positional `pairs_root` + required `--run-id` + `--port` (default 5000), calls `create_app`, runs `app.run(host="127.0.0.1", port=args.port)`.
- **Files created:** `apollo/scripts/eval_grade.py`.

## Known Stubs

None — every UI control is wired. The `/reveal/<nnn>` endpoint surfaces real `runs.jsonl` data when it exists and a graceful `{checkpoint_path: null, iteration: null}` fallback when it doesn't. The "unrenderable" worklist state correctly fires when `eval/<run_id>/response.wav` is missing on disk (D-13 path).

## Threat Flags

None new. The single network surface is Flask's dev server bound to 127.0.0.1 by `eval_grade.py` (RESEARCH §Anti-Patterns); no auth needed for a single-user localhost tool. Path-traversal at the nnn route variable is mitigated by set-membership validation against `enumerate_heldout` BEFORE any Path construction (PATTERNS S4, covered by `test_pair_view_path_traversal_returns_404` + `test_audio_path_traversal_blocked`).

## Self-Check: PASSED

- FOUND: apollo/eval/web/app.py
- FOUND: apollo/eval/web/templates/index.html
- FOUND: apollo/eval/web/templates/pair.html
- FOUND: apollo/eval/web/static/style.css
- FOUND: apollo/eval/web/static/grade.js
- FOUND: apollo/scripts/eval_grade.py
- FOUND: tests/test_eval_web.py
- FOUND: commit e0ab02e
- FOUND: commit f12380d
- FOUND: commit 96e833e

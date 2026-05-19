---
phase: 01-tokenizer-ingest
plan: 01
subsystem: tokenizer
tags: [scaffold, vocab, bins, ingest-error, tdd]
requirements_completed: [TOK-01, TOK-02, TOK-03, TOK-04]
dependency_graph:
  requires: []
  provides:
    - "apollo.tokenizer.Vocab (frozen integer constants — token ID contract)"
    - "apollo.tokenizer.DURATION_EDGES (25 log-spaced edges 0.030–1.500 s)"
    - "apollo.tokenizer.quantize_duration / decode_duration"
    - "apollo.tokenizer.quantize_time_shift / decode_time_shift"
    - "apollo.tokenizer.quantize_velocity / decode_velocity"
    - "apollo.ingest.IngestError (pair_path, reason)"
    - "Pip-installable `apollo` package (editable mode)"
  affects:
    - "All Phase 1 follow-on plans (01-02..01-05) — import Vocab + IngestError"
    - "Phase 2 model embedding table — must be sized to Vocab.VOCAB_SIZE (256)"
    - "Phase 2 training packer — must use Vocab.BOS/EOS/SEP IDs (109/110/111)"
tech_stack:
  added:
    - "Python package layout (apollo/, apollo/tokenizer/, apollo/ingest/, apollo/scripts/, tests/)"
    - "pyproject.toml (PEP 621, setuptools backend)"
    - "pytest (dev extra)"
  patterns:
    - "Frozen @dataclass for compile-time-constant integer tables"
    - "Module-level numpy constants computed once at import time (DURATION_EDGES)"
    - "Path-first, reason-second exception construction (IngestError)"
key_files:
  created:
    - "pyproject.toml"
    - "apollo/__init__.py"
    - "apollo/tokenizer/__init__.py"
    - "apollo/tokenizer/vocab.py"
    - "apollo/tokenizer/bins.py"
    - "apollo/ingest/__init__.py"
    - "apollo/ingest/errors.py"
    - "apollo/scripts/__init__.py"
    - "tests/__init__.py"
    - "tests/test_vocab_layout.py"
  modified:
    - ".gitignore (added artifacts/, build/, dist/)"
decisions:
  - "Followed D-21 by locking N_DURATION = 24 (log-spaced from 30 ms to 1.5 s) in code, matching RESEARCH.md final vocab table"
  - "Rule 1 deviation: corrected quantize_time_shift bin_width formula from plan's `(60/bpm)/8` to `(60/bpm)*2/n_bins`. Plan's snippet was internally inconsistent with its own '0.03125 s, max=1.0 s' comment and with D-05 ('32 bins ≈ 2 beats at corpus tempo'). The spec wins; the snippet was wrong."
  - "Rule 1 deviation: capped quantize_duration output at N_DURATION - 1 to handle the upper-edge case (searchsorted side='right' returns 25 when input equals 1.500)."
metrics:
  duration_minutes: 3.5
  completed_date: "2026-05-19"
  tasks_completed: 2
  files_created: 10
  files_modified: 1
  tests_passing: 13
---

# Phase 01 Plan 01: Project Scaffold + Vocab/Bin Contract Summary

Frozen Vocab integer constants, log-spaced duration edges, and IngestError exception type are now importable from a pip-installable `apollo` package. Phase 1's downstream plans (and Phase 2's model embedding table) consume this contract directly.

## What Was Built

### Task 1 — Project Scaffold (`feat(01-01): scaffold apollo package`)

- `pyproject.toml` at repo root: PEP 621 metadata, `setuptools.build_meta` backend, `name = "apollo"`, version `0.1.0`, Python `>=3.9`, dependencies pinned: `torch>=2.8.0`, `torchaudio>=2.8.0`, `pretty_midi>=0.2.11`, `numpy>=1.24`. Dev extra: `pytest>=7.0`. `[tool.pytest.ini_options]` points `testpaths = ["tests"]`.
- Empty `__init__.py` files for `apollo/`, `apollo/tokenizer/`, `apollo/ingest/`, `apollo/scripts/`, `tests/`. `apollo/__init__.py` defines `__version__ = "0.1.0"`.
- `.gitignore` extended (idempotent — existing `*.pt`, `__pycache__/`, `.pytest_cache/` already present) with `build/`, `dist/`, `artifacts/`.
- `pip install -e ".[dev]"` succeeded; editable wheel built and installed.
- `pytest --collect-only` exits 0 (zero tests at scaffold stage — discovery worked).

### Task 2 — Vocab + bins + IngestError + tests (TDD: `test(...)` → `feat(...)`)

`apollo/tokenizer/vocab.py` — frozen dataclass with 15 named constants. Confirmation that the values match RESEARCH.md §"Vocab ID Layout" exactly:

| Constant         | Value | Range/Meaning                  |
| ---------------- | ----- | ------------------------------ |
| PITCH_MIN        | 36    | C2 (MIDI)                      |
| PITCH_MAX        | 72    | C5 (MIDI)                      |
| N_PITCH          | 37    | Inclusive 36..72               |
| N_TIME           | 32    | Time-shift bins                |
| N_VELOCITY       | 16    | Linear velocity bins           |
| N_DURATION       | 24    | Log-spaced duration bins (D-21)|
| TIME_OFFSET      | 0     | IDs 0..31                      |
| PITCH_OFFSET     | 32    | IDs 32..68                     |
| VELOCITY_OFFSET  | 69    | IDs 69..84                     |
| DURATION_OFFSET  | 85    | IDs 85..108                    |
| BOS              | 109   | Start of sequence              |
| EOS              | 110   | End of sequence                |
| SEP              | 111   | Call/response boundary         |
| ACTIVE_VOCAB     | 112   | Used in v1                     |
| VOCAB_SIZE       | 256   | Total allocation (144 reserved)|

`apollo/tokenizer/bins.py`:
- `DURATION_EDGES = np.logspace(np.log10(0.030), np.log10(1.500), num=25)` — 25 edges → 24 bins, monotonically increasing, computed at import time.
- `quantize_duration(d_sec)` clamps to `[0.030, 1.500]` then returns `searchsorted(side='right') - 1`, capped at 23.
- `decode_duration(bin_i)` returns geometric mean of bin edges.
- `quantize_time_shift(dt, bpm=120, n_bins=32)` uses `bin_width = (60/bpm) * 2 / n_bins` (= 0.03125 s at 120 bpm, 32 bins), raises `ValueError` on out-of-range.
- `decode_time_shift(bin_i, bpm=120, n_bins=32)` mirrors the formula.
- `quantize_velocity(vel)` clamps to 1..127, returns `min(15, (v-1)*16 // 127)`.
- `decode_velocity(bin_i)` returns the bin's 1-based MIDI center.

`apollo/ingest/errors.py`:
- `class IngestError(Exception)` — `__init__(pair_path, reason)`, stores both as attrs, `str(e) == f"[{pair_path}] {reason}"`.

`apollo/tokenizer/__init__.py` and `apollo/ingest/__init__.py` export the public surface.

`tests/test_vocab_layout.py` — 13 test functions covering TOK-01..TOK-04: exact constant match, contiguous-no-overlap layout, frozen-dataclass enforcement, special-tokens-after-notes, DURATION_EDGES shape + endpoints + monotonicity, duration quantize endpoints + clamping, decode-in-range, time-shift basics + roundtrip + out-of-range, velocity endpoints, decode-in-MIDI-range, IngestError attr+str.

## Verification

```
$ ./venv/bin/python -m pytest tests/test_vocab_layout.py
============================== 13 passed in 0.04s ==============================
```

All 13 tests pass. All plan-level verification commands pass:
- `pip install -e ".[dev]"` exit 0
- `python -c "from apollo.tokenizer import Vocab, DURATION_EDGES, quantize_duration; from apollo.ingest import IngestError"` exit 0
- `grep -F 'artifacts/' .gitignore` matches; `grep -F '*.pt' .gitignore` matches

## Must-Haves Truths Check

| Truth | Status |
|------|--------|
| Python package `apollo` is installable in editable mode | PASS — `pip install -e .` exit 0 |
| Vocab constants are frozen and importable via `from apollo.tokenizer import Vocab` | PASS — frozen dataclass; import OK |
| `Vocab.VOCAB_SIZE == 256` and `Vocab.ACTIVE_VOCAB == 112` | PASS — asserted in `test_vocab_constants_exact_match` |
| `IngestError` carries `pair_path` and `reason` | PASS — asserted in `test_ingest_error_carries_path_and_reason` |
| Duration bin edges are 25 log-spaced floats from 0.030 to 1.500 | PASS — asserted in `test_duration_edges_shape_and_endpoints` |
| pytest runs and `tests/test_vocab_layout.py` passes | PASS — 13/13 |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Off-by-one in `quantize_duration` at upper edge**
- **Found during:** Task 2 GREEN run.
- **Issue:** Plan's interface snippet uses `int(np.searchsorted(DURATION_EDGES, d, side='right')) - 1`. When `d == 1.500` (the final edge), `searchsorted(side='right')` returns 25, giving `bin_i = 24` — out of the intended `0..23` range.
- **Fix:** Cap the result with `max(0, min(23, bin_i))`. Documented inline with a comment explaining the upper-edge case.
- **Files modified:** `apollo/tokenizer/bins.py`
- **Commit:** `d4f3d10`

**2. [Rule 1 - Bug] Wrong bin_width formula in `quantize_time_shift`**
- **Found during:** Task 2 GREEN run.
- **Issue:** Plan's interface snippet uses `bin_width = (60.0 / tempo_bpm) / 8.0`. At 120 bpm this gives 0.0625 s/bin (and 32 * 0.0625 = 2.0 s range), which contradicts both (a) the plan's own inline comment "`32nd-note width = (60 / 120) / 8 = 0.03125 s; max = 32 * 0.03125 = 1.0 s`" (the *value* 0.03125 is correct but the equation `/8` is wrong arithmetically) and (b) CONTEXT.md D-05 "32 bins ≈ 2 beats at corpus tempo". The spec intent is unambiguous: bin_width = 0.03125 s at 120 bpm, max ≈ 1.0 s = ~2 beats.
- **Fix:** `bin_width = (60.0 / tempo_bpm) * 2.0 / n_bins`. At 120 bpm with 32 bins: (60/120)*2/32 = 0.03125 s ✓. Generalises cleanly to other tempos.
- **Verification:** `test_quantize_time_shift_basics` (0.0 → 0, 0.03125 → 1, 31×0.03125 → 31) and `test_decode_time_shift_roundtrip` (quantize ∘ decode = identity for all 32 bins) pass.
- **Files modified:** `apollo/tokenizer/bins.py` (also added `n_bins` parameter to `decode_time_shift` so encode and decode stay symmetric)
- **Commit:** `d4f3d10`

### Auth Gates
None.

### Architectural Changes (Rule 4)
None.

## Test Results

```
tests/test_vocab_layout.py::test_vocab_constants_exact_match PASSED      [  7%]
tests/test_vocab_layout.py::test_vocab_ranges_contiguous_no_overlap PASSED [ 15%]
tests/test_vocab_layout.py::test_vocab_is_frozen PASSED                  [ 23%]
tests/test_vocab_layout.py::test_special_tokens_unique_and_after_notes PASSED [ 30%]
tests/test_vocab_layout.py::test_duration_edges_shape_and_endpoints PASSED [ 38%]
tests/test_vocab_layout.py::test_quantize_duration_endpoints_and_clamping PASSED [ 46%]
tests/test_vocab_layout.py::test_decode_duration_in_bin_range PASSED     [ 53%]
tests/test_vocab_layout.py::test_quantize_time_shift_basics PASSED       [ 61%]
tests/test_vocab_layout.py::test_quantize_time_shift_out_of_range_raises PASSED [ 69%]
tests/test_vocab_layout.py::test_decode_time_shift_roundtrip PASSED      [ 76%]
tests/test_vocab_layout.py::test_quantize_velocity_endpoints PASSED      [ 84%]
tests/test_vocab_layout.py::test_decode_velocity_in_midi_range PASSED    [ 92%]
tests/test_vocab_layout.py::test_ingest_error_carries_path_and_reason PASSED [100%]

============================== 13 passed in 0.04s ==============================
```

13 / 13 passing. Zero warnings.

## pyproject.toml Dependencies (exact)

```toml
dependencies = [
    "torch>=2.8.0",
    "torchaudio>=2.8.0",
    "pretty_midi>=0.2.11",
    "numpy>=1.24",
]

[project.optional-dependencies]
dev = ["pytest>=7.0"]
```

## Commits

| Task | Type | Hash | Message |
| ---- | ---- | ---- | ------- |
| 1 | feat | `47d98ec` | scaffold apollo package with pyproject and empty modules |
| 2 (RED) | test | `69ef3ed` | add failing vocab layout + bin contract tests |
| 2 (GREEN) | feat | `d4f3d10` | implement frozen Vocab, bin helpers, and IngestError |

TDD gate sequence intact: `test(...)` precedes `feat(...)` for Task 2.

## Known Stubs

None. All exports are wired to real implementations.

## Next Plan Hooks

Plan 01-02 (Tokenizer encoder/decoder) will:
- `from apollo.tokenizer import Vocab, quantize_time_shift, quantize_velocity, quantize_duration` to encode `pretty_midi` Note objects → token IDs.
- Wrap `ValueError` from `quantize_time_shift` in `IngestError(pair_path, ...)` per D-04/D-16 abort policy.
- Apply the `PITCH_MIN..PITCH_MAX` window check (D-04 abort, not clamp) before computing `PITCH_OFFSET + (pitch - PITCH_MIN)`.

## Self-Check: PASSED
- FOUND: pyproject.toml
- FOUND: apollo/__init__.py
- FOUND: apollo/tokenizer/__init__.py
- FOUND: apollo/tokenizer/vocab.py
- FOUND: apollo/tokenizer/bins.py
- FOUND: apollo/ingest/__init__.py
- FOUND: apollo/ingest/errors.py
- FOUND: apollo/scripts/__init__.py
- FOUND: tests/__init__.py
- FOUND: tests/test_vocab_layout.py
- FOUND: commit 47d98ec
- FOUND: commit 69ef3ed
- FOUND: commit d4f3d10

---
phase: 03-corpus-inference
reviewed: 2026-05-19T00:00:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - apollo/scripts/generate.py
  - apollo/scripts/train.py
  - tests/test_generate.py
  - tests/test_train_real.py
findings:
  critical: 0
  warning: 3
  info: 2
  total: 5
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-05-19
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Four Phase 3 source files were reviewed: the inference CLI (`generate.py`), the
production training CLI (`train.py`), and their respective test suites. The code
is well-structured, the documented design decisions are correctly reflected in the
implementation (scheduler-per-batch, `weights_only=False`, double `unsqueeze`),
and the error handling coverage is solid. No security vulnerabilities or
data-loss bugs were found.

Three warnings require attention before the corpus training run:

1. `estimate_tempo()` in `generate.py` raises `ValueError` for single-note MIDI
   files — the broad `except Exception` catches it, but the user sees
   "UNEXPECTED ERROR" with no actionable guidance.
2. The CSV file opened in `train.py` is not closed if an exception fires during
   the training loop (no `finally` guard), leaving the file handle open.
3. `test_generate_n_samples_naming` implicitly depends on
   `test_generate_smoke_creates_response_midi` having populated `response_001.mid`
   — a silent ordering dependency that will produce a confusing failure if tests
   are ever run in isolation.

Two info items note the `Vocab()` constructed fresh in `generate.py` (ignoring the
checkpoint-saved vocab dict) and a minor magic-number in the test fixture.

---

## Warnings

### WR-01: `estimate_tempo()` raises `ValueError` on single-note MIDI

**File:** `apollo/scripts/generate.py:162`

**Issue:** `pretty_midi.PrettyMIDI.estimate_tempo()` raises `ValueError("Can't
provide a global tempo estimate when there are fewer than two notes")` for any
call MIDI file with exactly one note (or an empty note list). The current handler
at line 209 catches this as a generic `Exception` and prints "UNEXPECTED ERROR:
ValueError(…)" with return code 2, giving the user no actionable diagnosis.
Given that the corpus constraint is 2–6 notes per phrase (CLAUDE.md), a
single-note call is a real user mistake that should produce a clear message.

**Fix:**
```python
# After the call_mid_path.exists() check, before the main try block:
try:
    call_bpm = float(pretty_midi.PrettyMIDI(str(call_mid_path)).estimate_tempo())
except ValueError as e:
    print(
        f"ERROR: cannot estimate tempo from {call_mid_path} "
        f"(need ≥2 notes per D-13): {e}",
        file=sys.stderr,
    )
    return 1
```

Alternatively, fall back to a default BPM (e.g. 120.0) with a warning, since
`load_notes` already has its own tempo-tolerance guard:
```python
try:
    call_bpm = float(pretty_midi.PrettyMIDI(str(call_mid_path)).estimate_tempo())
except ValueError:
    call_bpm = 120.0
    print(
        "WARNING: cannot estimate tempo (fewer than 2 notes); defaulting to 120 BPM",
        file=sys.stderr,
    )
```

---

### WR-02: CSV file handle not closed on exception during training loop

**File:** `apollo/scripts/train.py:157-185`

**Issue:** `csv_file` is opened at line 157 inside the outer `try` block. The
`csv_file.close()` call at line 184 is only reached on the happy path. If
`train_epoch`, `_evaluate_heldout_loss`, or `csv_writer.writerow` raises an
exception, the `except` clauses at lines 215–220 print and return, but
`csv_file` is never closed. On a multi-hour training run this leaves a dangling
file descriptor.

**Fix:** Wrap the open call with a context manager or add a `finally` block:
```python
# Replace lines 153-161 and 184-185 with a context manager approach:
csv_ctx = (
    open(csv_path, "w", newline="")
    if not args.no_csv
    else contextlib.nullcontext()
)
with csv_ctx as csv_file:
    csv_writer = (
        csv.DictWriter(csv_file, fieldnames=["epoch", "train_loss", "held_loss"])
        if csv_file is not None
        else None
    )
    if csv_writer is not None:
        csv_writer.writeheader()
    # ... training loop unchanged ...
```

Or a minimal `finally` guard:
```python
try:
    # ... all existing training code ...
finally:
    if csv_file is not None:
        csv_file.close()
```

---

### WR-03: Implicit test ordering dependency in `test_generate_n_samples_naming`

**File:** `tests/test_generate.py:79-80`

**Issue:** `test_generate_n_samples_naming` asserts
`assert (pair_dir / "response_001.mid").exists()` before running, relying on
`test_generate_smoke_creates_response_midi` having already written that file.
Both tests share the `module`-scoped `mock_ckpt` fixture, so pytest's default
sequential ordering makes this pass, but:

- Running `pytest tests/test_generate.py::test_generate_n_samples_naming` in
  isolation will fail with a confusing assertion error unrelated to the code
  under test.
- Any future reordering (e.g., via `pytest-randomly`) silently breaks this test.

**Fix:** Remove the pre-condition assertion and instead call `generate.main` once
inside the test to establish the baseline, or rename the assertion to make the
dependency explicit:
```python
def test_generate_n_samples_naming(mock_ckpt):
    ckpt_path, pair_dir = mock_ckpt
    # Establish baseline: generate the first response if not already present
    if not (pair_dir / "response_001.mid").exists():
        generate.main([str(ckpt_path), str(pair_dir / "call.mid"), str(pair_dir / "call.wav")])
    rc = generate.main([
        str(ckpt_path), str(pair_dir / "call.mid"), str(pair_dir / "call.wav"),
        "--n", "3", "--max-tokens", "8",
    ])
    assert rc == 0
    for i in [2, 3, 4]:
        assert (pair_dir / f"response_{i:03d}.mid").exists()
```

---

## Info

### IN-01: `generate.py` constructs a fresh `Vocab()` and ignores the checkpoint-saved vocab dict

**File:** `apollo/scripts/generate.py:165`

**Issue:** The checkpoint stores a `vocab` dict (saved by `ingest` at artifact
time) precisely so that future inference can detect schema drift. `generate.py`
constructs `vocab = Vocab()` unconditionally and never reads `ckpt["vocab"]`.
This is currently harmless because `Vocab` is a frozen dataclass with fixed
constants, but once the schema is extended (reserved IDs 112–255 are allocated
for future CCs), a checkpoint trained against a different vocab layout will
silently decode with the wrong offsets.

**Suggestion:** Add a best-effort version check at load time:
```python
saved_vocab = ckpt.get("vocab", {})
live_active = Vocab().ACTIVE_VOCAB
if saved_vocab.get("ACTIVE_VOCAB", live_active) != live_active:
    print(
        f"WARNING: checkpoint vocab ACTIVE_VOCAB={saved_vocab['ACTIVE_VOCAB']} "
        f"!= current {live_active}; token offsets may be mismatched.",
        file=sys.stderr,
    )
vocab = Vocab()
```

---

### IN-02: Magic number `7` repeated across all five train tests without explanation

**File:** `tests/test_train_real.py:21,39,57,73,90`

**Issue:** Every test calls `_make_pairs(pairs_root, 7)`. The comment on line 21
explains the intent ("6 train + 1 held_out"), but lines 39, 57, 73, and 90
repeat `7` without comment. If the held-out split logic changes (e.g., the
threshold moves from `n // 7` to `n // 8`), all tests will need updating with
no obvious link between the magic number and the invariant it encodes.

**Suggestion:** Introduce a named constant:
```python
# At module level:
_N_PAIRS = 7  # 6 train + 1 held-out (ApolloDataset split boundary)
```
Then reference `_N_PAIRS` in each test body. The existing comment on
`test_train_cli_smoke_creates_checkpoint` can move to the constant definition.

---

_Reviewed: 2026-05-19_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

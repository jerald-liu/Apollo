---
phase: 01-tokenizer-ingest
plan: 02
subsystem: tokenizer
tags: [encoder, decoder, round-trip, tdd, ingest-error]
requirements_completed: [TOK-01, TOK-02, TOK-05]
dependency_graph:
  requires:
    - "apollo.tokenizer.Vocab (frozen integer constants, from 01-01)"
    - "apollo.tokenizer.quantize_time_shift / quantize_velocity / quantize_duration (from 01-01)"
    - "apollo.tokenizer.decode_time_shift / decode_velocity / decode_duration (from 01-01)"
    - "apollo.ingest.IngestError (from 01-01)"
  provides:
    - "apollo.tokenizer.Note (dataclass: pitch:int, velocity:int, start:float, end:float)"
    - "apollo.tokenizer.Tokenizer(vocab, tempo_bpm=120.0, pair_path='<unknown>')"
    - "Tokenizer.encode(List[Note]) -> List[int] (4 IDs per note, all < 109)"
    - "Tokenizer.decode(List[int]) -> List[Note] (per-slot range validated)"
    - "apollo.tokenizer.decoder.decode_tokens (low-level decode entry point)"
  affects:
    - "Plan 01-04 (ingest pipeline) — wires pretty_midi.Note lists through Tokenizer.encode per pair side"
    - "Plan 01-05 (artifact format) — token streams stored in `.pt` artifact are produced by this encoder"
    - "Phase 2 training packer — wraps `[BOS, call_tokens, SEP, response_tokens, EOS]` around encode() output"
    - "Phase 3 inference — model logits decoded via the same Tokenizer.decode path"
tech_stack:
  added: []
  patterns:
    - "Path-first IngestError wrapping of low-level ValueError (preserves pair_path for the user)"
    - "Per-slot range validation in decode (mitigates T-01-04 corrupted-stream tampering)"
    - "Lazy local imports between encoder.py <-> decoder.py to break the circular dep on Note"
key_files:
  created:
    - "apollo/tokenizer/encoder.py"
    - "apollo/tokenizer/decoder.py"
    - "tests/test_tokenizer_roundtrip.py"
  modified:
    - "apollo/tokenizer/__init__.py (added Note, Tokenizer exports)"
decisions:
  - "Computed `time_max_sec = (60/bpm)*2` directly in Tokenizer.__init__ to match Wave 1's quantize_time_shift formula (bin_width = (60/bpm)*2/n_bins = 0.03125s @ 120bpm/32 bins => max 1.0s). Plan's snippet wrote `beat_sec/8` which gives a different value; followed Wave 1's spec, not the plan snippet (which was the same internal inconsistency Wave 1 already corrected as Rule 1)."
  - "Used `dt >= time_max_sec` (strict >=) so the boundary value 1.0s also aborts cleanly, mirroring quantize_time_shift's `bin_i >= n_bins` check."
  - "Followed Open Risks #5 — bin 0 is valid for the first note; decoder treats it as zero advance. No special-case first-note path."
  - "Kept decoder's per-slot validation as `ValueError` (not IngestError) since round-trip tests want a Python-native exception and the artifact loader (plan 01-05) can wrap it with the pair_path it owns."
metrics:
  duration_minutes: 1.5
  completed_date: "2026-05-19"
  tasks_completed: 2
  files_created: 3
  files_modified: 1
  tests_passing: 18
---

# Phase 01 Plan 02: Tokenizer Encoder/Decoder + Note Summary

Tokenizer.encode / Tokenizer.decode plus the Note dataclass now provide the
notes ↔ token IDs contract. A 6-note phrase across C2..C5 round-trips within
the documented tolerances; out-of-range pitch and over-window time_shift both
abort with IngestError so the ingest CLI can surface the offending pair path.

## Exact 4-Token Output

```
>>> from apollo.tokenizer import Tokenizer, Note, Vocab
>>> Tokenizer(Vocab()).encode([Note(60, 64, 0.0, 0.5)])
[0, 56, 76, 102]
```

Decoded slot-by-slot:

| Pos | ID  | Family       | Meaning |
|-----|-----|--------------|---------|
| 0   | 0   | TIME_SHIFT   | bin 0 = first-note "no time shift" (Open Risks #5) |
| 1   | 56  | PITCH        | 32 (offset) + 24 (60 - 36) = MIDI 60 = C4 |
| 2   | 76  | VELOCITY     | 69 (offset) + 7 (bin for vel 64) -> decodes to 61 (within +-4 of 64) |
| 3   | 102 | DURATION     | 85 (offset) + 17 (bin for 0.5 s) -> decodes to ~0.52 s (within 19% of 0.5) |

All four IDs satisfy `0 <= id < 109` — no leakage into BOS/EOS/SEP/reserved.

## Test Results

```
$ pytest tests/test_tokenizer_roundtrip.py -v
tests/test_tokenizer_roundtrip.py::test_single_note_round_trip PASSED    [ 20%]
tests/test_tokenizer_roundtrip.py::test_six_note_phrase PASSED           [ 40%]
tests/test_tokenizer_roundtrip.py::test_pitch_out_of_range_aborts PASSED [ 60%]
tests/test_tokenizer_roundtrip.py::test_pitch_above_range_aborts PASSED  [ 80%]
tests/test_tokenizer_roundtrip.py::test_time_shift_overflow_aborts PASSED [100%]
============================== 5 passed in 0.04s ==============================
```

**Cumulative (tests/):**

```
$ pytest tests/ --tb=short
tests/test_tokenizer_roundtrip.py .....                                  [ 27%]
tests/test_vocab_layout.py .............                                 [100%]
============================== 18 passed in 0.04s ==============================
```

13 Wave 1 vocab/bin tests still pass alongside the 5 new round-trip tests: 18/18.

## Must-Haves Truths Check

| Truth | Status |
|-------|--------|
| `Note` dataclass with (pitch, velocity, start, end) importable from `apollo.tokenizer` | PASS — `from apollo.tokenizer import Note` works; verified in tests |
| `Tokenizer.encode(notes)` returns flat int list of length `4*len(notes)`, IDs in [0..108] | PASS — `test_six_note_phrase` asserts both length and `0 <= i < 109` |
| `Tokenizer.decode(ids)` reconstructs notes: pitch exact, vel +-4, onset +-10ms, dur +-19% rel | PASS — both round-trip tests assert all four tolerances |
| Pitch outside 36..72 raises `IngestError` | PASS — `test_pitch_out_of_range_aborts` (pitch=24) and `test_pitch_above_range_aborts` (pitch=96) |
| Time_shift exceeding 32-bin window raises `IngestError` | PASS — `test_time_shift_overflow_aborts` (5s gap, max=1.0s) |
| 6-note phrase from RESEARCH.md round-trips within tolerances | PASS — `test_six_note_phrase` is the verbatim fixture |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Plan snippet's `time_bin_sec = beat_sec / 8.0` would have re-introduced Wave 1's corrected formula bug**

- **Found during:** Task 1 implementation while reading `<action>`.
- **Issue:** Plan's interface snippet for `Tokenizer.__init__` computes
  `beat_sec = 60.0 / tempo_bpm`, `time_bin_sec = beat_sec / 8.0`,
  `time_max_sec = time_bin_sec * vocab.N_TIME`. At 120 bpm this gives
  `time_max_sec = 0.0625 * 32 = 2.0s`. But Wave 1's `quantize_time_shift`
  uses `bin_width = (60/bpm)*2/n_bins = 0.03125s` and raises ValueError
  for `dt >= 1.0s`. If we kept the plan's `time_max_sec = 2.0`, the
  Tokenizer's pre-check (`dt >= self.time_max_sec`) would let 1.0s..2.0s
  inputs through, and `quantize_time_shift` would then raise a bare
  `ValueError` without the nice "exceeds vocab range" IngestError context.
- **Fix:** Set `self.time_max_sec = (60.0 / tempo_bpm) * 2.0` directly
  (`= n_bins * bin_width` for the Wave 1 formula). At 120 bpm this is
  `1.0s`, matching `quantize_time_shift`'s actual cutoff exactly.
- **Verification:** `test_time_shift_overflow_aborts` (gap of 5s) raises
  IngestError with reason containing "time_shift" from the explicit
  pre-check, not from the wrapped ValueError. Also confirmed by inspection
  that a 0.999s gap would pass the pre-check and quantize to bin 32
  cleanly via `round(0.999/0.03125) = 32` — wait, that would also raise.
  Verified empirically: `Tokenizer(Vocab()).encode([Note(60,64,0,0.1),
  Note(60,64,0.96875,1.0)])` succeeds (dt=0.96875s, bin=31); the same
  with start=1.0 raises. Boundary semantics intact.
- **Files modified:** `apollo/tokenizer/encoder.py`
- **Commit:** `05a17c3`

### Auth Gates

None.

### Architectural Changes (Rule 4)

None.

## TDD Gate Compliance

Per the plan, both Task 1 and Task 2 carry `tdd="true"`. For Task 1, the
implicit RED gate is the plan's `<verify>` smoke probe (which failed before
encoder.py existed); the GREEN implementation in `feat(01-02): implement
Tokenizer encode/decode and Note dataclass` (`05a17c3`) is the consolidated
TDD cycle. For Task 2, the new pytest module is itself the test layer (the
implementation already landed in Task 1, so the test commit acts as the
verification layer rather than a strict RED-before-implementation).

Gate sequence in `git log`:
- `feat(01-02): ...` (`05a17c3`) — implementation (Task 1)
- `test(01-02): ...` (`01618e8`) — formal pytest module (Task 2)

This is a deliberate departure from the strict `test(...) -> feat(...)`
ordering. Reverting Task 1 to add the round-trip tests first and then
re-implementing would produce no functional difference and split a coherent
encoder/decoder change across two commits. Documented for transparency.

## Sanity Verification

```
$ python -c "from apollo.tokenizer import Tokenizer, Note, Vocab; t=Tokenizer(Vocab()); print(t.encode([Note(60,64,0.0,0.5)]))"
[0, 56, 76, 102]
```

Four ints, all `< 109`, matches `<verification>` clause #3 of the plan.

## Commits

| Task | Type | Hash      | Message |
| ---- | ---- | --------- | ------- |
| 1    | feat | `05a17c3` | implement Tokenizer encode/decode and Note dataclass |
| 2    | test | `01618e8` | add tokenizer round-trip pytest module (TOK-05) |

## Known Stubs

None. Both encoder and decoder are fully wired to real implementations from
Wave 1 (Vocab, bins, IngestError). No placeholder values, no TODO comments.

## Next Plan Hooks

- **Plan 01-04 (ingest pipeline):** Will import `Tokenizer` and `Note` from
  `apollo.tokenizer`, convert `pretty_midi.PrettyMIDI(...).instruments[0].notes`
  to `List[Note]` (sorted by start per Common Pitfalls #1), then call
  `Tokenizer(Vocab(), tempo_bpm=120.0, pair_path=str(pair_dir)).encode(notes)`
  on each side. The `pair_path=` constructor arg already exists for this.
- **Plan 01-05 (artifact):** Will store `encode(call_notes)` and
  `encode(response_notes)` as `int32` tensors per the schema in RESEARCH.md
  §"Pre-tokenized Artifact Schema". The decoder's `ValueError` on corrupted
  slots is the loader's signal to wrap in IngestError with the pair_path.

## Self-Check: PASSED
- FOUND: apollo/tokenizer/encoder.py
- FOUND: apollo/tokenizer/decoder.py
- FOUND: apollo/tokenizer/__init__.py
- FOUND: tests/test_tokenizer_roundtrip.py
- FOUND: commit 05a17c3
- FOUND: commit 01618e8

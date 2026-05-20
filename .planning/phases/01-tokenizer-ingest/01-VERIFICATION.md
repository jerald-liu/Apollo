---
phase: 01-tokenizer-ingest
verified: 2026-05-19T22:26:29Z
status: passed
score: 5/5 success criteria verified; 1 latent import-ordering bug found and closed in-phase (see Resolution log)
re_verification: true
gaps: []
resolved:
  - issue: "apollo.tokenizer ↔ apollo.ingest circular import (Note imported from apollo.tokenizer.encoder by apollo.ingest.midi while encoder.py was mid-init via apollo.ingest.errors → apollo.ingest.__init__ → artifact → midi)."
    fix_commit: "see `fix(01): break apollo.tokenizer ↔ apollo.ingest circular import`"
    changes:
      - "Hoisted Note dataclass into leaf module apollo/tokenizer/types.py."
      - "Lazy-imported IngestError inside Tokenizer.encode() so apollo.tokenizer no longer triggers apollo.ingest at module-load time."
      - "Re-exported Note from apollo.tokenizer.encoder for backward compatibility."
      - "Added tests/test_import_hygiene.py — 3 subprocess regression tests covering standalone import of apollo.tokenizer, apollo.ingest, and legacy encoder.Note path."
    test_evidence: "49/49 pytest pass (was 46/46 + 3 new regression tests); `python -c 'from apollo.tokenizer import Vocab; print(Vocab.VOCAB_SIZE)'` exits 0 in a clean subprocess."
human_verification: []
---

# Phase 1: Tokenizer & Ingest — Verification Report

**Phase Goal:** The pipeline can ingest any `data/pairs/NNN/` folder and produce training-ready tensors.

**Verified:** 2026-05-19T22:26:29Z
**Status:** gaps_found (1 latent circular-import bug; all five ROADMAP success criteria pass on their own merits)
**Re-verification:** No — initial verification

## Goal Achievement — ROADMAP Success Criteria

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | MIDI round-trips through tokenizer with pitches, velocities, onsets preserved within quantization tolerance | VERIFIED | `tests/test_tokenizer_roundtrip.py::test_six_note_phrase` PASS; manual round-trip of `[Note(60,64,0,.5), Note(62,80,.5,.75), Note(67,100,.75,1.0)]` confirms pitch exact, velocity ±4, onset ±50 ms |
| 2 | Ingest over mock pairs produces tokenized + mel tensors with no silent failures | VERIFIED | `tests/test_ingest_smoke.py::test_ingest_ten_pairs_end_to_end` PASS — asserts shape (96,128), dtype float32/int32, len % 4 == 0, 10 entries from 10 mock pairs |
| 3 | Missing or malformed `call.wav` causes pipeline to report offending pair and abort (no silent skip) | VERIFIED | `test_missing_call_wav_aborts` raises `IngestError` with `call.wav` and `000` in message; `test_cli_exit_code_one_on_ingest_error` confirms CLI exits 1 with `INGEST FAILED: ... call.wav` on stderr |
| 4 | Held-out split is deterministic — same 20% on every run regardless of authoring order | VERIFIED | `is_heldout` uses `int(sha1(nnn).hexdigest(), 16) % 5 == 0` (`apollo/ingest/split.py:38`); `test_split_is_deterministic_across_runs` + `test_renaming_changes_split` pin formula |
| 5 | Vocab includes BOS, EOS, SEP, and contiguous reserved ranges for future pitch bend / mod wheel / CC | VERIFIED | `Vocab` frozen dataclass: BOS=109, EOS=110, SEP=111, ACTIVE_VOCAB=112, VOCAB_SIZE=256 (144 reserved tail slots); `test_vocab_constants_exact_match` + `test_special_tokens_unique_and_after_notes` |

**Score: 5/5 success criteria verified.**

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `apollo/tokenizer/vocab.py` | Frozen Vocab with documented layout | VERIFIED | `@dataclass(frozen=True)` confirmed at runtime (`v.__dataclass_params__.frozen == True`); 15 named integer constants match RESEARCH.md §"Vocab ID Layout" exactly |
| `apollo/tokenizer/bins.py` | 25 log-spaced edges 0.030–1.500 s + quantize/decode helpers | VERIFIED | `DURATION_EDGES.shape == (25,)`, endpoints 0.030/1.500, `quantize_time_shift` formula `(60/bpm)*2/n_bins` matches D-05 |
| `apollo/tokenizer/encoder.py` | `Note`, `Tokenizer.encode` (4 IDs/note) | VERIFIED | Round-trip on 3-note phrase: `[0, 56, 76, 102, 16, 58, 78, 98, 8, 63, 81, 98]` — all IDs < 109 (no leakage into BOS/EOS/SEP/reserved) |
| `apollo/tokenizer/decoder.py` | `Tokenizer.decode` reconstructs notes | VERIFIED | Inverse of encode (round-trip pitch exact, velocity ±4, onset ±50 ms) |
| `apollo/ingest/errors.py` | `IngestError(pair_path, reason)` | VERIFIED | `str(IngestError("p","r")) == "[p] r"`; carries both attrs |
| `apollo/ingest/audio.py` | `MelExtractor` → (96, 128) float32 | VERIFIED | Live check on 1 s of zeros at 44100 Hz: `shape=(96, 128), dtype=torch.float32`; size cap 10 MB, duration cap 30 s, pad = `log(1e-8) ≈ -18.42` |
| `apollo/ingest/pairs.py` | `discover_pairs` with symlink-escape rejection | VERIFIED | `resolved.relative_to(root_path)` (`pairs.py:71`); `test_symlink_escape_aborts` |
| `apollo/ingest/midi.py` | `load_notes` with single-instrument, tempo, mono guards | VERIFIED | Empty-MIDI before tempo (handles `estimate_tempo` raise); ±2 bpm tempo; MAX_NOTES_PER_PAIR=1000; MONOPHONIC_EPS=1e-3 |
| `apollo/ingest/split.py` | `is_heldout`, `normalize_nnn` | VERIFIED | sha1 mod 5 == 0; deterministic across calls; `is_heldout('000')=False, '006'=True, '009'=True` matches 01-04 SUMMARY fixture |
| `apollo/ingest/artifact.py` | `ingest`, `save_artifact`, `load_artifact`, `SCHEMA_VERSION=1` | VERIFIED | `SCHEMA_VERSION == 1`; artifact dict has `schema_version`, `vocab` (17 keys), `mel_config`, `pairs`, `metadata`; `load_artifact` validates schema |
| `apollo/scripts/ingest_corpus.py` | CLI with exit codes 0/1/2 | VERIFIED | `--help` → exit 0; `/nonexistent/path` → exit 1 with `INGEST FAILED: [/nonexistent/path] corpus root not found...`; exit 2 path present for unexpected exceptions |
| `apollo/ingest/mock.py` | `synthesize_pair` test helper | VERIFIED | `test_synthesize_pair_creates_three_files` PASS — writes `call.mid`, `call.wav`, `response.mid` under `<out_dir>/<nnn>/` |

## Key Link Verification

| From | To | Via | Status |
|------|----|-----|--------|
| `ingest()` | `discover_pairs` | Direct call `apollo/ingest/artifact.py:83` | WIRED |
| `ingest()` | `MelExtractor` | Direct call `apollo/ingest/artifact.py:103` | WIRED |
| `ingest()` | `Tokenizer.encode` | Direct call `apollo/ingest/artifact.py:97-101` | WIRED |
| `ingest()` | `load_notes` | Direct call `apollo/ingest/artifact.py:91-95` | WIRED |
| `ingest()` | `is_heldout` | Direct call `apollo/ingest/artifact.py:104` | WIRED |
| CLI | `ingest()` + `save_artifact` | `apollo/scripts/ingest_corpus.py:44-45` | WIRED |
| CLI | `IngestError` exit-1 path | `apollo/scripts/ingest_corpus.py:50-52` | WIRED |
| Round-trip | `Tokenizer.encode → tensors → save_artifact → load_artifact → torch.equal` | `test_artifact_round_trip` | WIRED |

## Behavioral Verification

| Check | Result | Detail |
|-------|--------|--------|
| `pytest tests/` (all) | **46/46 passed** | 2.05 s; 30 warnings (torchaudio 2.9 deprecation noise — not in scope) |
| `python -m apollo.scripts.ingest_corpus --help` | exit 0 | Argparse usage printed |
| `python -m apollo.scripts.ingest_corpus /nonexistent/path` | exit 1 | `INGEST FAILED: [/nonexistent/path] corpus root not found or not a directory` on stderr |
| End-to-end ingest, 10 mock pairs | 0.014 s | 700× under the 10 s test threshold (`test_end_to_end_under_ten_seconds`) |
| Live `MelExtractor()(<1 s zeros>)` | (96, 128) float32 | Shape + dtype contract met |
| Live `Tokenizer().encode([Note(60,64,0,.5)])` | `[0, 56, 76, 102]` | All IDs < 109; matches 01-02 SUMMARY |
| `pytest tests/test_vocab_layout.py` (in isolation) | **ImportError at collection** | Circular import (see gap below) |

## Requirements Coverage

| Req | Description (REQUIREMENTS.md) | Plan(s) | Status | Evidence |
|-----|-------------------------------|---------|--------|----------|
| TOK-01 | Monophonic MIDI event tokenizer (pitch + velocity + timing + duration) | 01-01, 01-02 | SATISFIED | `Tokenizer.encode` emits 4 tokens/note from `Note(pitch, velocity, start, end)`; monophonic enforced in `load_notes` |
| TOK-02 | Quantized-grid time + duration bins | 01-01, 01-02 | SATISFIED | `quantize_time_shift` 32 bins at 32nd-note grid; `quantize_duration` 24 log-spaced bins |
| TOK-03 | Vocab includes BOS/EOS/SEP | 01-01 | SATISFIED | `Vocab.BOS=109, EOS=110, SEP=111`; `test_special_tokens_unique_and_after_notes` |
| TOK-04 | Reserved contiguous range for pitch-bend / mod-wheel / CC | 01-01 | SATISFIED | IDs 112..255 (144 slots) reserved; `VOCAB_SIZE=256`; existing checkpoints stay valid |
| TOK-05 | Round-trip preserves pitch / velocity / onset within tolerance | 01-02, 01-05 | SATISFIED | `test_six_note_phrase` + `test_artifact_round_trip` (torch.equal on tokens AND mel) |
| DATA-01 | User can author and export call/response pairs in Ableton with Operator | 01-05 | SATISFIED | Pipeline accepts the documented folder layout; mock helper proves the shape ingest needs; authoring side is human, code-side contract complete |
| DATA-02 | Each pair lives at `data/pairs/NNN/{call.mid, call.wav, response.mid}` | 01-04 | SATISFIED | `discover_pairs` enforces all three files; `PairPath` dataclass; NNN gaps allowed (D-17, `test_nnn_gaps_allowed`) |
| DATA-03 | Pipeline reads `data/pairs/*/` and tokenizes pairs into training tensors | 01-04 | SATISFIED | `ingest()` returns `pairs: List[{nnn, is_heldout, call_tokens(int32), response_tokens(int32), call_mel(96,128)f32}]` |
| DATA-04 | 20% held-out split, deterministic across runs | 01-04 | SATISFIED | `is_heldout` sha1 mod 5; `test_split_is_deterministic_across_runs`; CLI happy-path shows `2 heldout` on `[000..009]` matching fixture |
| COND-01 | Mel extractor produces fixed-shape mel-spectrogram at documented sr/hop/n_mels | 01-03 | SATISFIED | SR=22050, n_fft=2048, hop=512, n_mels=128, fixed (96, 128); documented in `audio.py` |
| COND-04 | Missing or malformed `call.wav` → pipeline reports offending pair and aborts | 01-03, 01-05 | SATISFIED | `MelExtractor` raises `IngestError(pair_path, ...)` on stat / load / size-cap failure; `test_missing_call_wav_aborts` |

**Coverage: 11/11 phase requirements satisfied.**

## Anti-Patterns Scan

| File | Pattern | Severity | Notes |
|------|---------|----------|-------|
| (all phase files) | TODO / FIXME / XXX / HACK | none | grep returns 0 across `apollo/**.py` |
| (all phase files) | `placeholder` / `coming soon` / `not implemented` | none | 0 hits |
| `apollo/tokenizer/encoder.py:116` | Lazy local import (`from apollo.tokenizer.decoder import decode_tokens`) | INFO | Intentional — documented as breaking the encoder/decoder Note cycle. Does NOT break the larger ingest/tokenizer cycle (see gap). |
| `apollo/ingest/artifact.py:151` | `torch.load(..., weights_only=False)` | INFO | Documented as trusted-local-only (T-01-14 disposition); appropriate for our-file-only loader |
| `apollo/ingest/mock.py` | Test helper exposed in production `__init__` | INFO | Re-exported as `synthesize_pair`; module docstring flags it test-only; production CLI does not import it |

## Test Quality Audit

| Test File | Linked Reqs | Active | Skipped | Circular | Assertion Level | Verdict |
|-----------|-------------|--------|---------|----------|-----------------|---------|
| `test_vocab_layout.py` | TOK-01..04 | 13 | 0 | No | Value (exact int equality) | STRONG |
| `test_tokenizer_roundtrip.py` | TOK-05 | 5 | 0 | No | Value (round-trip equality within tolerance) | STRONG |
| `test_mel_extractor.py` | COND-01, COND-04 | 8 | 0 | No | Value (shape, dtype, pad value, threat caps) | STRONG |
| `test_split_determinism.py` | DATA-04 | 6 | 0 | No | Value (formula pinned, ratio band) | STRONG |
| `test_ingest_smoke.py` | DATA-01..03 + COND-01 + TOK-05 | 5 | 0 | No | Behavioral (end-to-end, torch.equal round-trip) | STRONG |
| `test_error_handling.py` | COND-04, DATA-03 | 9 | 0 | No | Behavioral (subprocess CLI exit codes) | STRONG |

**Disabled tests on requirements:** 0.
**Circular tests detected:** 0 — `test_artifact_round_trip` uses `torch.equal` on (original ingest → save → load); that's intra-system consistency, not external-oracle parity. Acceptable for Phase 1 (T-01-19 disposition: cross-machine bit-exact not a v1 requirement).
**Insufficient assertions:** 0.
**Quantity coverage:** Plan-by-plan claimed counts (13 + 5 + 8 + 6 + 5 + 9) sum to **46**, matches actual `pytest tests/ -q` output.

## Gaps Summary

**1 gap found** — a latent circular-import bug not surfaced by the ROADMAP success criteria but flagged here because it will trip Phase 2 trainers and any user-facing script that imports `apollo.tokenizer` before `apollo.ingest`.

### Gap 1: Circular import between `apollo.tokenizer` and `apollo.ingest`

- **Reproduction:** `python -c "from apollo.tokenizer import Vocab"` → `ImportError: cannot import name 'Note' from partially initialized module 'apollo.tokenizer.encoder'`
- **Also reproduces:** `pytest tests/test_vocab_layout.py` (in isolation, not via the full suite) → collection error
- **Why full suite passes:** pytest collects modules alphabetically; `test_error_handling.py` runs first, imports `apollo.ingest`, fills `sys.modules`. By the time `test_vocab_layout.py` is collected, both packages are already loaded and the cycle is invisible.
- **Cycle path:** `apollo.tokenizer.__init__` → `.encoder` → `apollo.ingest.errors` → `apollo.ingest.__init__` → `.artifact` → `.midi` → `apollo.tokenizer.encoder` (partially initialized — ImportError fires here)
- **Severity:** WARNING. Does not block any current test or ROADMAP success criterion. Will block Phase 2 work when a trainer / inference script does `from apollo.tokenizer import Vocab, Tokenizer` as its first import.
- **Suggested fixes (any one suffices):**
  1. Move `Note` dataclass into a new leaf module `apollo/tokenizer/types.py` that imports nothing from `apollo.ingest`; have `encoder.py` and `midi.py` both import `Note` from there.
  2. In `apollo/ingest/midi.py`, defer `from apollo.tokenizer.encoder import Note` to inside `load_notes` (mirrors the lazy import already used in `Tokenizer.decode`).
  3. Restructure `apollo/ingest/__init__.py` to lazily import `.artifact` and `.midi` on attribute access (more invasive).
- **Regression test to add:** `subprocess.run([sys.executable, "-c", "from apollo.tokenizer import Vocab"]).returncode == 0`.

---

## Fix Plan Recommendation

Single focused plan (`01-06-PLAN.md`):

- **Objective:** Eliminate the circular import so any module can import `apollo.tokenizer` first without priming `apollo.ingest`.
- **Tasks:**
  1. Move `Note` dataclass from `apollo/tokenizer/encoder.py` to a new leaf `apollo/tokenizer/types.py` (no `apollo.ingest` imports). Re-export `Note` from `apollo/tokenizer/__init__.py` to preserve the public API.
  2. Update `apollo/ingest/midi.py` and `apollo/tokenizer/encoder.py` to import `Note` from `apollo.tokenizer.types`.
  3. Add `tests/test_import_order.py` with a subprocess test asserting `from apollo.tokenizer import Vocab` returns exit 0 in a fresh interpreter.
- **Re-verify:** `pytest tests/test_vocab_layout.py` (in isolation) passes; full `pytest tests/` still 47/47.

---

*Verified: 2026-05-19T22:26:29Z*
*Verifier: Claude (gsd-verifier)*

# Phase 1: Tokenizer & Ingest - Pattern Map

**Mapped:** 2026-05-19
**Files analyzed:** ~17 new files (no modifications — orphan branch)
**Analogs found:** 0 / 17 (in-repo)

## Headline

**No in-repo analogs exist.** The active branch `call-and-response-v1` is an orphan containing only `CLAUDE.md`, `README.md`, `.gitignore`. There is no Python source code on this branch to copy patterns from.

The `deprecated` branch contains prior implementations (`src/representation.py`, `src/spectral.py`, etc.) but CONTEXT.md (lines 91, 101-102) explicitly forbids reuse: *"do NOT plan to reuse"* and *"cherry-picking pieces will reintroduce the assumptions."* The planner MUST NOT instruct the executor to read, import, or copy from those files.

**Consequence for the planner:** Pattern guidance for Phase 1 comes from RESEARCH.md (`01-RESEARCH.md`), not from this PATTERNS.md. RESEARCH.md already contains complete, concrete code patterns (Vocab dataclass, Tokenizer class signature, MelExtractor class, IngestError class, hash split function, artifact schema, mock generator, test structure). The planner should cite RESEARCH.md sections directly in plan actions instead of citing a file in the codebase.

## File Classification

All files are **new**. Role/data-flow classification only — the "Closest Analog" column is N/A by design.

| New File | Role | Data Flow | In-Repo Analog | RESEARCH.md Section |
|----------|------|-----------|----------------|---------------------|
| `pyproject.toml` | config | n/a | none | Module Layout |
| `apollo/__init__.py` | package init | n/a | none | Module Layout |
| `apollo/tokenizer/__init__.py` | package init | n/a | none | Module Layout |
| `apollo/tokenizer/vocab.py` | model (frozen dataclass) | constants | none | Vocab ID Layout |
| `apollo/tokenizer/bins.py` | utility | transform (quantize) | none | Duration Bin Scheme |
| `apollo/tokenizer/encoder.py` | service (pure fn) | transform (notes→ids) | none | Tokenizer Design / Encoder algorithm |
| `apollo/tokenizer/decoder.py` | service (pure fn) | transform (ids→notes) | none | Tokenizer Design / Decoder algorithm |
| `apollo/ingest/__init__.py` | package init | n/a | none | Module Layout |
| `apollo/ingest/errors.py` | model (exception class) | n/a | none | Error Handling |
| `apollo/ingest/pairs.py` | service | file-I/O (discover+validate) | none | Module Layout, Error Handling |
| `apollo/ingest/midi.py` | service | file-I/O (parse) | none | Code Examples / MIDI load |
| `apollo/ingest/audio.py` | service | file-I/O (load+resample+mel) | none | Mel Pipeline |
| `apollo/ingest/split.py` | utility (pure fn) | transform (hash) | none | Deterministic Split |
| `apollo/ingest/artifact.py` | service | file-I/O (save/load .pt) | none | Pre-tokenized Artifact Schema |
| `apollo/ingest/mock.py` | utility (test helper) | file-I/O (synthesize) | none | Mock Pair Generation |
| `apollo/scripts/__init__.py` | package init | n/a | none | Module Layout |
| `apollo/scripts/ingest_corpus.py` | CLI entry | request-response (argv→exit code) | none | Error Handling / CLI behavior |
| `tests/__init__.py` | package init | n/a | none | Module Layout |
| `tests/test_tokenizer_roundtrip.py` | test | n/a | none | Round-Trip Test |
| `tests/test_vocab_layout.py` | test | n/a | none | Vocab ID Layout |
| `tests/test_split_determinism.py` | test | n/a | none | Deterministic Split |
| `tests/test_error_handling.py` | test | n/a | none | Error Handling |
| `tests/test_ingest_smoke.py` | test | n/a | none | Mock Pair Generation |

## Pattern Assignments

Per-file pattern guidance is entirely sourced from RESEARCH.md. Rather than duplicate that content here, planner actions should reference:

| File | Reference (in `01-RESEARCH.md`) |
|------|---------------------------------|
| `apollo/tokenizer/vocab.py` | "Vocab ID Layout" — the `@dataclass(frozen=True) Vocab` block defines every constant |
| `apollo/tokenizer/bins.py` | "Duration Bin Scheme" — `DURATION_EDGES`, `quantize_duration`, `decode_duration` |
| `apollo/tokenizer/encoder.py` | "Tokenizer Design / Encoder algorithm" — full pseudocode |
| `apollo/tokenizer/decoder.py` | "Tokenizer Design / Decoder algorithm" — full pseudocode |
| `apollo/ingest/errors.py` | "Error Handling / Pattern" — `IngestError` class verbatim |
| `apollo/ingest/pairs.py` | "Error Handling / Call sites" table — folder validation cases |
| `apollo/ingest/midi.py` | "Code Examples / MIDI load" + "Common Pitfalls #1" (sort by start) |
| `apollo/ingest/audio.py` | "Mel Pipeline" — full `MelExtractor` class |
| `apollo/ingest/split.py` | "Deterministic Split" — `normalize_nnn`, `is_heldout` functions |
| `apollo/ingest/artifact.py` | "Pre-tokenized Artifact Schema" — dict structure; "Common Pitfalls #4" (`weights_only=False`) |
| `apollo/ingest/mock.py` | "Mock Pair Generation" — `synthesize_pair` function |
| `apollo/scripts/ingest_corpus.py` | "Error Handling / Top-level CLI behavior" — `main()` with exit-code map |
| `tests/test_tokenizer_roundtrip.py` | "Round-Trip Test / Concrete test structure" — full pytest module |
| `tests/test_*` (others) | Distributed across RESEARCH.md sections per the requirements table |

## Shared Patterns (cross-cutting)

These apply to multiple files. Source for all of them is RESEARCH.md, not in-repo code.

### Error reporting
**Pattern:** All pair-level failures raise `IngestError(pair_path, reason)`. Path-first, reason-second. CLI converts `IngestError` → exit 1; any other exception → exit 2.
**Source:** RESEARCH.md "Error Handling" section.
**Applies to:** `pairs.py`, `midi.py`, `audio.py`, `encoder.py`, `ingest_corpus.py`.

### Tensor dtype contract
**Pattern:** Tokens are `int32`; mel is `float32`; everything CPU-resident at save time (Phase 2 moves to MPS).
**Source:** RESEARCH.md "Pre-tokenized Artifact Schema / Dtypes".
**Applies to:** `audio.py`, `encoder.py`, `artifact.py`.

### Determinism
**Pattern:** No `random`, no time-based seeds, no filesystem walk order dependence. Hash-only for split; pair iteration sorted by NNN string before save.
**Source:** RESEARCH.md "Deterministic Split", D-15, D-20.
**Applies to:** `pairs.py`, `split.py`, `artifact.py`.

### Schema versioning
**Pattern:** Artifact dict carries `schema_version: 1`; loader asserts it matches.
**Source:** RESEARCH.md "Pre-tokenized Artifact Schema / Schema evolution policy".
**Applies to:** `artifact.py` and any Phase 2 loader (downstream).

## No Analog Found

Every file in this phase falls into this bucket. The active branch is empty; using `deprecated` is explicitly forbidden by CONTEXT.md.

## Conceptual Analogs on `deprecated` (do NOT instruct executor to read)

For planner awareness only. These are *conceptual* siblings — same problem domain, different (piano-era) solution. The planner SHOULD NOT cite these in plan actions; they are listed here so the planner can recognize if a researcher reference inadvertently echoes a deprecated-branch pattern.

| Phase 1 file | Conceptual sibling on `deprecated` | Why not reused |
|--------------|-----------------------------------|----------------|
| `apollo/tokenizer/{vocab,encoder,decoder}.py` | `src/representation.py` | Piano-era pitch range (88 keys), MAESTRO-shaped vocab, NoteOn/NoteOff event style — incompatible with D-01/D-03/D-07 |
| `apollo/tokenizer/bins.py` | `src/representation.py` (bin helpers within) | Different bin philosophy; would smuggle in tempo/timing assumptions |
| `apollo/ingest/audio.py` | `src/spectral.py`, `src/streaming_representation.py` | Streaming/online mel design for live inference; v1 needs offline fixed-shape `(96, 128)` only |
| `apollo/scripts/ingest_corpus.py` | `scripts/preprocess.py` | Piano dataset (MAESTRO) preprocessing; pair-folder convention is new |
| `tests/test_*` | `tests/unit/test_representation.py`, `test_spectral.py` | Test piano-era invariants; new tests target FM/call-response invariants |

**Planner instruction:** If a plan action ever feels like it should say "see `src/representation.py` for inspiration," rewrite it to cite the corresponding RESEARCH.md section instead. The deprecated code carries assumptions that the user has explicitly rejected (CONTEXT.md lines 21, 91, 101-102).

## Metadata

**Analog search scope:** working tree of `call-and-response-v1` (only `CLAUDE.md`, `README.md`, `.gitignore` present); planning artifacts under `.planning/`.
**Deprecated branch:** inventoried via `git ls-tree` for conceptual-analog flagging only; no file contents read or extracted.
**Files scanned (active branch):** 0 source files (none exist).
**Pattern extraction date:** 2026-05-19
**Pattern source of truth for the planner:** `01-RESEARCH.md`.

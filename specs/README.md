# Apollo Specs

This directory holds **English-language behavioural specs** for each module in
Apollo. Each spec enumerates invariants as atomic, numbered, testable
statements (e.g. `R5.3`, `S2.2`, `M4.4`, `P1.1`). Tests under `tests/` reference
these IDs in their names or docstrings so that any test failure can be traced
back to a specific contractual clause.

## Why

- **Shared vocabulary.** A failure in `test_tokens_to_events_roundtrip` is
  easier to triage when its docstring says "R7.5" and R7.5 is a one-line
  English sentence.
- **Change control.** Modifying a spec is a deliberate act. Modifying code
  that violates a spec will surface in CI via a failing test.
- **Scope fence.** Things not in the spec are explicitly not guaranteed.

## Layout

| Spec | Covers | Test file |
|---|---|---|
| `representation.md` | `src/representation.py` | `tests/unit/test_representation.py` |
| `spectral.md`       | `src/spectral.py`       | `tests/unit/test_spectral.py` |
| `model.md`          | `src/model.py`          | `tests/unit/test_model.py` |
| `preprocess.md`     | `scripts/preprocess.py` | `tests/integration/test_preprocess.py` |
| `interfaces.md`     | module boundaries       | `tests/integration/test_interfaces.py` |

## Clause ID prefixes

- `R*` — representation
- `S*` — spectral
- `M*` — model
- `P*` — preprocess
- `IR→M.*`, `IR→P.*`, `IS→R.*`, `IM→G.*` — interface contracts

## Workflow

1. **Before changing behaviour:** update the relevant spec clause. The spec is
   the source of truth.
2. **Add or update the matching test** that enforces the new clause.
3. **Implement** the code change. Tests should pass.

New invariants get new IDs, never reuse an old one — even if its test was
deleted, since git history will reference the old number.

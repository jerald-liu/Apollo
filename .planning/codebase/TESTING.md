# Testing Patterns

**Analysis Date:** 2026-05-13

## Test Framework

**Runner:**
- `pytest` >= 7.4
- Config: `pytest.ini` (project root)

**Assertion Libraries:**
- `pytest.approx` for float comparisons
- `np.testing.assert_allclose` / `np.testing.assert_array_equal` for array comparisons
- `torch.allclose` for tensor comparisons with tolerance
- `torch.isfinite` for NaN/inf guards

**Run Commands:**
```bash
# All tests (unit + integration)
venv/bin/python -m pytest

# Unit tests only (fast, no disk I/O beyond tmp_path)
venv/bin/python -m pytest -m unit

# Integration tests only
venv/bin/python -m pytest -m integration

# Specific file
venv/bin/python -m pytest tests/unit/test_model.py

# With coverage
venv/bin/python -m pytest --cov=src --cov-report=term-missing

# Smoke training check (200 steps, tiny model)
make smoke
```

## Test File Organization

**Location:** Separate `tests/` directory (not co-located with source)

```
tests/
├── conftest.py              # Shared fixtures (all tests)
├── unit/
│   ├── test_model.py        # src/model.py — 30 test functions
│   ├── test_representation.py  # src/representation.py — 46 test functions
│   └── test_spectral.py     # src/spectral.py — 37 test functions
└── integration/
    ├── test_interfaces.py   # Cross-module seam contracts — 13 test functions
    └── test_preprocess.py   # scripts/preprocess.py — 16 test functions
```

**Naming:** `test_<file>.py` → `Test<Class>` → `test_<SpecID>_<description>`

## Test Structure

**Module-level marker declaration (all test files):**
```python
pytestmark = pytest.mark.unit       # or pytest.mark.integration
```

**Class grouping:** All tests are grouped into `Test*` classes by the component or method being tested:
```python
class TestSpectralEncoder:
    def test_M1_1_shape(self): ...
    def test_M1_2_arbitrary_batch_and_time(self): ...
    def test_M1_4_finite(self): ...

class TestApolloModelForward:
    def test_M4_2_logits_shape(self, tiny_model): ...
    def test_M4_8_causal_masking(self, tiny_model): ...
```

**Spec ID naming convention:** Every test function name embeds the spec clause ID it enforces:
```
test_M1_1_shape          → model.md clause M1.1
test_R5_3_length_without_timbre → representation.md clause R5.3
test_IR_M_1_tokens_in_embedding_range → interfaces.md clause IR→M.1
test_P2_5_window_count   → preprocess.md clause P2.5
test_S4_2_attack_is_max_onset → spectral.md clause S4.2
```

**File-level docstrings** cite the spec being covered:
```python
"""Tests for src/model.py.

All model tests run on CPU with a tiny config to keep CI fast.
Each test cites the clause ID from specs/model.md it enforces.
"""
```

## Fixtures (conftest.py)

All fixtures live in `tests/conftest.py`. They produce synthetic data so CI runs without the MAESTRO dataset or network access.

**MIDI fixtures:**
```python
@pytest.fixture
def synthetic_midi_path(tmp_path):
    """20-note ascending C major scale with sustain pedal. Uses tmp_path."""
    ...

@pytest.fixture
def corrupt_midi_path(tmp_path):
    """A .mid file containing invalid bytes — tests error handling."""
    ...
```

**Audio fixtures:**
```python
@pytest.fixture
def synthetic_audio_arrays():
    """Hand-built dict mimicking SpectralAnalyzer.analyze_audio_to_arrays() output.
    200 frames of random data (seeded at 42). No librosa required."""
    rng = np.random.default_rng(42)
    return {"times": ..., "centroid": ..., "flux": ..., ...}

@pytest.fixture
def synthetic_audio_file(tmp_path):
    """Writes a real 1-second two-tone WAV via soundfile. Needed for librosa tests."""
    ...
```

**Model fixture (file-local, not in conftest):**
```python
TINY_CFG = dict(vocab_size=380, d_model=32, nhead=2, num_layers=2,
                max_seq_len=64, user_embed_dim=8, spectral_dim=21,
                n_timbre_outputs=5, dropout=0.0)

@pytest.fixture
def tiny_model():
    torch.manual_seed(0)
    m = ApolloModel(**TINY_CFG)
    m.eval()
    return m
```

The `TINY_CFG` / `tiny_model` pattern (small model for CPU speed) is defined locally in `tests/unit/test_model.py` and mirrored in `tests/integration/test_interfaces.py` as `TINY`.

## Mocking

**No mocking framework used** (no `unittest.mock`, no `pytest-mock`). All external dependencies are replaced with:
- **Synthetic fixtures** for audio/MIDI data (see above)
- **`tmp_path`** pytest built-in for all file I/O
- **Seeded random** (`np.random.default_rng(42)`, `torch.manual_seed(0)`) for determinism

**What is NOT mocked:**
- `pretty_midi` — real objects created in fixtures
- `torch` operations — real CPU tensors
- `librosa` — real analysis on the synthetic WAV fixture

## Spec Coverage Enforcement

A pre-commit hook enforces that every spec clause has a test:

```python
# scripts/check_spec_coverage.py
# Parses specs/*.md for clause IDs matching **R5.3**, **IR→M.1** etc.
# Verifies a test function containing the normalised ID exists in tests/**/*.py
# Normalisation: R5.3 → r_5_3, IR→M.1 → ir_m_1
```

Run manually:
```bash
python scripts/check_spec_coverage.py   # exits 1 if any clause is uncovered
```

This means: adding a spec clause without a test causes commit to fail.

## Test Types

**Unit tests (`tests/unit/`, `pytest.mark.unit`):**
- One class per public function/class in the source module
- CPU-only, tiny configs (d_model=32, 2 layers, seq_len=64)
- Use `tmp_path` for all file writes; no disk reads from repo
- All fixtures are synthetic — no MAESTRO data required
- Covers: tensor shapes, dtype correctness, range constraints (0-1 sigmoid output), roundtrip properties, boundary conditions (empty input, out-of-range clamp, degenerate stats)

**Integration tests (`tests/integration/`, `pytest.mark.integration`):**
- Test seams between two modules, not internals of one
- `test_interfaces.py`: verifies the 4 interface contracts (R→M, R→P, S→R, M→G)
- `test_preprocess.py`: drives the full MIDI→tokens→windows pipeline end-to-end

**E2E tests:**
- Marker `e2e` is registered in `pytest.ini` but no test files use it yet
- `make smoke` runs `scripts/train.py --config configs/smoke.yaml` (200 steps, tiny model) as a manual E2E check — this is not collected by pytest

## Assertion Patterns

**Tensor shapes:**
```python
assert out.shape == (B, T, 32)
assert out["logits"].shape == (B, T, TINY_CFG["vocab_size"])
```

**Tensor values — range:**
```python
assert out.min() >= 0.0
assert out.max() <= 1.0
assert torch.isfinite(out).all()
```

**Tensor values — approximate equality:**
```python
assert torch.allclose(out_prefix, out_full, atol=1e-5)   # causal masking test
```

**Array comparisons:**
```python
np.testing.assert_allclose(arr[0, :5], [0.1, 0.2, 0.3, 0.4, 0.5], atol=1e-6)
np.testing.assert_array_equal(n.dynamic_envelope, env)
```

**Float comparisons:**
```python
assert a.frame_duration == pytest.approx(512 / 22050)
assert ccs[0].time == pytest.approx(0.0, abs=1e-4)
assert stats["brightness"]["min"] == pytest.approx(np.percentile(vals, 2))
```

**Structural assertions:**
```python
assert isinstance(result, list)
assert all(isinstance(e, ApolloEvent) for e in events)
assert set(entry.keys()) == {"mean", "std", "delta"}
assert "error" in result
assert "error" not in result
```

**Roundtrip / invariant assertions:**
```python
assert torch.equal(tokens[:, :5], prompt)   # prompt preserved after generate
assert a.pitch == b.pitch                   # pitch survives tokenize→detokenize
assert abs(a.delta_time - b.delta_time) <= dt_tol + 1e-6   # within quantization error
```

## Coverage Gaps

**Not currently tested:**
- `src/inference_server.py` — `ApolloInferenceServer` class has zero test coverage. No unit tests for OSC handler methods, `_generate_response`, `_stream_generate`, `_generate_response_streaming`, `_load_model`, or `_warmup`. This is the largest untested surface.
- `src/streaming_representation.py` — `midi_to_streaming_tokens`, `streaming_tokens_to_events`, `streaming_notes_to_midi`, `encode_note_on`, `encode_note_off` are not covered in any test file. The streaming vocab (259 tokens) is only exercised indirectly via `test_interfaces.py` imports.
- `scripts/train.py` — Training loop, dataset class, checkpoint save/resume, DDP, mixed precision, and wandb logging have no automated tests. Only the smoke run via `make smoke` validates this path.
- `scripts/generate.py`, `scripts/spectral_analysis.py`, `scripts/synthesize.py`, `scripts/train_poc.py`, `scripts/train_spectral.py` — no tests at all.
- `modal_train.py` — Modal cloud orchestration is untested locally.
- `src/model.py` — `MelEncoder`, `CodecHead`, `CausalTransformerLayer`, and `CausalTransformer` have no dedicated test classes. Only `SpectralEncoder`, `TimbrePredictor`, and `ApolloModel` are tested.
- KV-cache correctness for multi-step generation — `TestGenerate` tests shape and prompt preservation but does not verify that cached-decode output equals non-cached decode output token-by-token.

---

*Testing analysis: 2026-05-13*

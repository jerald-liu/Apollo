# Coding Conventions

**Analysis Date:** 2026-05-13

## Naming Patterns

**Files:**
- `snake_case.py` for all modules: `representation.py`, `spectral.py`, `streaming_representation.py`, `inference_server.py`
- Scripts follow the same convention: `preprocess.py`, `train.py`, `check_spec_coverage.py`
- No barrel `__init__.py` files; `src/` is added to `sys.path` at runtime

**Classes:**
- `PascalCase` throughout: `ApolloModel`, `SpectralAnalyzer`, `CausalTransformerLayer`, `NoteSpectralProfile`, `ApolloInferenceServer`
- nn.Module subclasses follow the same rule: `SpectralEncoder`, `MelEncoder`, `TimbrePredictor`, `CodecHead`

**Functions:**
- `snake_case` for all functions and methods: `midi_to_events`, `events_to_tokens`, `compute_normalization_stats`
- Private helpers prefixed with underscore: `_init_weights`, `_expand_spectral_to_tokens`, `_generate_response`, `_resolve_device`, `_quantize`, `_dequantize`
- Module-level private helpers (not intended to be exported) use the same underscore prefix in `streaming_representation.py`: `_quantize`, `_dequantize`

**Constants:**
- `ALL_CAPS_SNAKE` for module-level constants: `VOCAB_SIZE`, `TOKEN_OFFSETS`, `TIME_SHIFT_BINS`, `CONTINUOUS_DIM`, `TRAJECTORY_DIM`, `TOKENS_PER_EVENT`
- nn.Module class-level constants use `ALL_CAPS`: `N_CODEBOOKS`, `CODEBOOK_SIZE` (see `CodecHead` in `src/model.py`)

**Variables:**
- `snake_case` everywhere; short tensor variables use compact names consistent with ML idiom: `B`, `T`, `H`, `D` for batch/time/head/dim inside forward methods
- Config dicts use string keys matching argument names exactly: `"d_model"`, `"nhead"`, `"vocab_size"`

## Line Length and Formatting

- **Max line length:** 100 characters (`ruff.toml`)
- **Target version:** Python 3.11 (`ruff.toml`)
- No Black or Prettier configured; formatting is enforced only via Ruff's E9 (syntax errors)
- Alignment of related assignments is used in dense initialization blocks:

```python
self.nhead   = nhead
self.d_head  = d_model // nhead
self.d_model = d_model
self.scale   = self.d_head ** -0.5
```

## Linting Configuration

**Tool:** `ruff` (config at `ruff.toml`)

**Rules enabled:** `F` (pyflakes) + `E9` (syntax errors) only — intentionally minimal for research code

**Explicitly ignored:**
- `F401` — unused imports (OK)
- `F541` — f-strings without placeholders (OK)
- `F841` — unused local variables (OK)
- Tests additionally ignore `F811` (redefinition)

**Pre-commit hook:** `scripts/check_spec_coverage.py` runs on every commit to verify spec clause coverage. Not a formatting check — it enforces that every spec ID from `specs/*.md` has a corresponding test.

## Type Hints

Used consistently in all `src/` files. Style:

```python
# Function signatures always typed
def quantize(value: float, bins: np.ndarray) -> int: ...
def midi_to_events(
    midi_path: str,
    max_events: int = 2048,
    spectral_analyzer=None,            # untyped optional is acceptable
    audio_path: str = None,
    spectral_norm_stats: dict = None,
) -> List[ApolloEvent]: ...

# nn.Module forward methods use tensor annotations with inline shape comments
def forward(
    self,
    x: torch.Tensor,           # (B, T, C)
    past_kv: Optional[Tuple[torch.Tensor, torch.Tensor]] = None,
) -> Tuple[torch.Tensor, Tuple[torch.Tensor, torch.Tensor]]: ...
```

- `Optional[X]` used for nullable parameters (not `X | None` — codebase targets 3.9+ compatibility in practice)
- `List`, `Tuple`, `Dict` imported from `typing` (not the built-in lowercase generics)
- `list[X]` built-in generics appear in newer additions (`streaming_representation.py`, `inference_server.py`), reflecting Python 3.9+ availability

## Docstrings

**Module-level:** All `src/` and `scripts/` files have a module docstring explaining purpose, key concepts, usage. Format is plain prose, no specific docstring convention (not Google/NumPy style).

```python
"""Apollo spectral analysis — FFT-over-time feature extraction.

Extracts frame-level and note-level spectral features from audio,
aligned to MIDI events. ...
"""
```

**Class-level:** Present on all public classes; describes architectural role and key relationships.

**Method-level:** Present on non-trivial methods; uses a consistent `Args:` / `Returns:` block style for functions with multiple parameters:

```python
def forward(self, spectral_features: torch.Tensor) -> torch.Tensor:
    """
    Args:
        spectral_features: (B, T_events, spectral_dim) continuous features

    Returns:
        (B, T_events, d_model) projected spectral embeddings
    """
```

Tensor shape annotations are placed inline in the docstring `Args:` block as `(B, T, C)` tuples — not as separate documentation. Simple helper functions (`quantize`, `dequantize`) have one-line docstrings.

## Dataclass Usage

Dataclasses are used for structured data containers throughout `src/`:

- `ApolloEvent` in `src/representation.py` — musical event with spectral fields
- `SpectralFrame`, `NoteSpectralProfile` in `src/spectral.py` — frame and note-level audio features
- `StreamNoteOn`, `StreamNoteOff` in `src/streaming_representation.py` — streaming event types
- `TrainConfig` in `scripts/train.py` — flat training configuration container

**Pattern for mutable defaults:** Always use `field(default_factory=...)` — never bare mutable defaults:

```python
@dataclass
class ApolloEvent:
    trajectory: np.ndarray = field(default_factory=lambda: np.full(TRAJECTORY_DIM, 0.0))
```

**Pattern for config dataclasses:** All fields have defaults; constructed by merging YAML into `dataclass(**cfg_dict)`. `asdict()` is used for serialization to checkpoint `meta.json`.

## Import Organization

**Order used throughout:**
1. Standard library (`argparse`, `sys`, `time`, `threading`, `pathlib`, `dataclasses`, `math`, `copy`)
2. Third-party (`numpy`, `torch`, `torch.nn`, `librosa`, `pretty_midi`, `yaml`, `pythonosc`)
3. Local (`from model import ...`, `from representation import ...`)

Local imports use explicit `sys.path.insert(0, ...)` rather than package install:

```python
# In scripts/
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

# In tests/conftest.py
ROOT = Path(__file__).parent.parent
for p in (SRC, SCRIPTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
```

No path aliases or `__init__.py` files. Absolute imports only.

## Error Handling

**Pattern in data processing functions:** Catch-all `except Exception as e` at process boundaries, return error dict instead of raising:

```python
def process_file(args):
    try:
        ...
        return {'tokens': tokens, 'n_events': len(events), ...}
    except Exception as e:
        return {'error': str(e), 'file': str(midi_path)}
```

**Pattern in OSC handlers:** Catch-all `except Exception as e` that sends error back over OSC rather than crashing the server:

```python
try:
    for event, timbre_row in self._stream_generate(prompt, n_gen):
        ...
except Exception as e:
    self.osc_client.send_message("/apollo/error", [str(e)])
```

**Pattern in data validation (defensive guards):** Return early with defaults rather than raising:

```python
if mask.sum() == 0:
    return NoteSpectralProfile(brightness=0.5, attack=0.5, ...)
```

**No custom exception classes** — plain `Exception` is caught everywhere. Logging uses `print(f"[Apollo] ...")` with the `[Apollo]` prefix for server-level messages.

## Tensor Shape Conventions

Shape annotations appear as inline comments next to tensor operations — this is a project-wide convention, not just in docstrings:

```python
Q = Q.view(B, T, H, D).transpose(1, 2)   # (B, H, T,  D)
K = K.view(B, T, H, D).transpose(1, 2)
```

Dimension variable names: `B` = batch, `T` = sequence length, `C` = channels/d_model, `H` = heads, `D` = head dimension, `N` = event count.

## Constants vs Config Dicts

Module-level constants encode the fixed vocabulary structure:

```python
TOKEN_OFFSETS = {
    'time_shift': 0,    # 0-99
    'pitch': 100,       # 100-227
    ...
}
VOCAB_SIZE = 380
```

Runtime hyperparameters live in YAML configs under `configs/` and are loaded into dataclasses (`TrainConfig`) or plain dicts (inference). Constants are never overridden at runtime; the streaming vocab (`VOCAB_SIZE = 259`) is a separate module (`streaming_representation.py`) rather than a config parameter.

## Comment Style

**Section separators:** Dash-line separators used inside long files to group related functions:

```python
# --- Quantization bins ---
# --- Token offsets ---
# --- Helper functions ---
```

**ASCII art diagrams:** Used in class docstrings for architecture description:

```python
"""
    Input:  token_emb + pos_emb + spectral_emb + user_emb
                ↓
            Transformer decoder (causal)
                ↓
            ┌───┴───┐
        token_head  timbre_head
"""
```

**Inline explanatory comments:** Present on non-obvious operations, especially tensor math.

---

*Convention analysis: 2026-05-13*

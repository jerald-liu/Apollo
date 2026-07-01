# Phase 7: Synth Automation (LFO) - Pattern Map

**Mapped:** 2026-06-02
**Files analyzed:** 5 (4 code/test extends + 1 doc extend)
**Analogs found:** 5 / 5 (all in-repo, all Phase-6 recent)

> This phase EXTENDS the Phase-6 synth. Every file modified already exists, and its best analog is its own current structure. The planner should mirror existing in-file discipline (the `_check_number` / `_OP_FIELDS` validation pattern, the `_build_name_index_map` runtime label resolution, the numeric-only `dsp_string` security rule, and the in-file pytest helpers) — not invent new shapes.

## File Classification

| File | Action | Role | Data Flow | Closest Analog | Match Quality |
|------|--------|------|-----------|----------------|---------------|
| `apollo/synth/spec.py` | extend | model / config (versioned schema + DSP source builder) | transform (params → DSP string) | itself (current `OperatorParams`/`FmParams`/`dsp_string`) | exact (self) |
| `apollo/synth/manifest.py` | extend | validator (untrusted-input boundary) | transform / request-response | itself (`_check_number`, `_OP_FIELDS`, version guard, op loop) | exact (self) |
| `apollo/synth/render.py` | extend | service (render engine driver) | streaming / file-I/O (params+notes → audio) | itself (`_build_name_index_map`, per-op slider-set loop, `_OP_SLIDER_FIELDS`) | exact (self) |
| `tests/test_synth_render.py` | extend | test | n/a | itself (`_fm_params`, `_manifest_dict`, `test_render_deterministic`, `test_mel_contract`, `test_no_clipping`, manifest-validation tests) | exact (self) |
| `data/pairs/CORPUS-CONVENTIONS.md` | extend | docs | n/a | itself (the `call_fm.json` schema section, lines 37-65) | exact (self) |

## Pattern Assignments

### `apollo/synth/spec.py` (model/config, transform)

**Analog:** itself. Three coordinated edits: bump version, add LFO dataclass+enums, branch `dsp_string`.

**Version bump pattern** (line 37): single module constant, "do not mutate without bumping" doc rule already in the header (lines 8-14).
```python
SPEC_VERSION = "1.0"   # → "1.1"
```

**Enum + frozen-dataclass pattern** (mirror `Algorithm` lines 40-51 and `OperatorParams` lines 54-75): the existing module already uses `from enum import IntEnum` (line 32) and `@dataclass(frozen=True)`. Add `LfoWave`/`LfoTarget` IntEnums and a frozen `LfoParams`; add `lfo: LfoParams | None = None` to `FmParams` (lines 78-88) as a trailing optional field so it stays hashable and the existing positional constructor calls do not break.
```python
class LfoWave(IntEnum):
    SINE = 0
    TRIANGLE = 1
    SQUARE = 2

class LfoTarget(IntEnum):
    LEVEL = 0   # tremolo
    PITCH = 1   # vibrato

@dataclass(frozen=True)
class LfoParams:
    rate: float
    depth: float
    wave: int
    target: int
```
Keep `operators: tuple[...]` (line 87) tuple convention; `lfo` defaults `None` so v1.0 callers are unchanged.

**Numeric-only DSP-string security rule** (the load-bearing boundary — `dsp_string` lines 100-177):
- The header doc (lines 24-27) and the docstring (lines 105-106) state: "substitutes NUMERIC params only. No string field from a manifest is ever interpolated." The LFO wiring MUST obey this. `lfo.wave`/`lfo.target` are routed through Faust `select3(int(lfo_wave), ...)` as **numeric hslider values**, never via Python string branching on the waveform name.
- Float substitution convention is `{float(x):.6f}` (lines 134-143). New `lfo_rate`/`lfo_depth` sliders follow the same `:.6f` formatting; `lfo_wave` follows the integer-step hslider form `hslider("lfo_wave", 0, 0, 2, 1)`.

**Backward-compat branch pattern** (the determinism guarantee — extend top of `dsp_string`):
```python
if p.lfo is None:
    return <exact existing v1.0 string — the current lines 119-177 body, unchanged>
```
Emit the Phase-6 string verbatim when `lfo is None` (RESEARCH Pitfall 1 — strictly safer than depth-0 wiring). Per-carrier targeting follows the existing template carrier names: `car` (STACK lines 152-159, PARALLEL_MODS 160-167), `car1`/`car2` (CARRIER_PAIR 168-175). Apply the global LFO to ALL carriers uniformly (RESEARCH A4 default).

**Per-op slider-name contract** (lines 132-145): existing sliders are `op{i}_ratio`/`op{i}_level` (+ ADSR baked as `en.adsr(...)` literals). New LFO sliders `lfo_rate`/`lfo_depth`/`lfo_wave` are declared in the LFO block ONLY when `lfo` is present, so they shift no existing indices in the no-lfo path. The docstring already documents that render.py resolves names→indices at runtime (lines 113-118) — extend that note to mention the lfo sliders.

---

### `apollo/synth/manifest.py` (validator, request-response)

**Analog:** itself. The whole module is the fail-loud trust boundary; the LFO block extends it without new shapes.

**Imports pattern** (lines 35-36): add `LfoParams, LfoTarget, LfoWave` to the existing `from apollo.synth.spec import ...`.
```python
from apollo.ingest.errors import IngestError
from apollo.synth.spec import SPEC_VERSION, Algorithm, FmParams, OperatorParams
```

**Bounds-as-module-constants pattern** (lines 38-61): mirror `RATIO_MIN, RATIO_MAX = ...` style. Add `LFO_RATE_MIN/MAX = 0.05, 20.0` and `LFO_DEPTH_MIN/MAX = 0.0, 1.0` near the other bounds.

**`_check_number` discipline** (lines 64-77) — the load-bearing validation primitive. It rejects bools, rejects non-`(int,float)`, rejects non-finite (`math.isfinite`), range-checks, and raises `IngestError(pair_path, f"{label} ...")` naming the pair. Reuse it directly for `lfo.rate`/`lfo.depth`. Missing keys are handled by `raw_lfo.get("rate")` → `None` → `_check_number` rejects (RESEARCH note, line 253).

**New enum-int checker** (mirror `algorithm` guard lines 104-109 which already does the "bool-reject + int-check + membership-check + IngestError" pattern):
```python
def _check_enum_int(value, pair_path, label, valid: set[int]) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise IngestError(pair_path, f"{label} must be an int, got {type(value).__name__}")
    if value not in valid:
        raise IngestError(pair_path, f"{label} {value} not in {sorted(valid)}")
    return value
```

**Version guard pattern** (lines 95-101) — the current guard is exact-equality `version != SPEC_VERSION`. This MUST relax to a set membership accepting `{"1.0","1.1"}`, AND add the cross-check "lfo present ⇒ version must be 1.1":
```python
SUPPORTED_VERSIONS = {"1.0", "1.1"}
...
if version not in SUPPORTED_VERSIONS:
    raise IngestError(pair_path, f"manifest spec_version {version!r} not in {sorted(SUPPORTED_VERSIONS)}")
```
Keep the existing message-shape so `test_manifest_bad_version` (asserts `match="spec_version"`) still passes for `"9.9"`.

**Optional-block validation pattern** (extend, placed after the `gain` block lines 131-133, before the `return`):
```python
lfo = None
raw_lfo = raw.get("lfo")
if raw_lfo is not None:
    if version != "1.1":
        raise IngestError(pair_path, "lfo block requires spec_version '1.1'")
    if not isinstance(raw_lfo, dict):
        raise IngestError(pair_path, f"lfo must be an object, got {type(raw_lfo).__name__}")
    rate  = _check_number(raw_lfo.get("rate"),  pair_path, "lfo rate",  LFO_RATE_MIN, LFO_RATE_MAX)
    depth = _check_number(raw_lfo.get("depth"), pair_path, "lfo depth", LFO_DEPTH_MIN, LFO_DEPTH_MAX)
    wave   = _check_enum_int(raw_lfo.get("wave"),   pair_path, "lfo wave",   {w.value for w in LfoWave})
    target = _check_enum_int(raw_lfo.get("target"), pair_path, "lfo target", {t.value for t in LfoTarget})
    lfo = LfoParams(rate=rate, depth=depth, wave=wave, target=target)
```
Then thread `lfo=lfo` into the `return FmParams(...)` (line 135).

Update the module docstring schema block (lines 9-20, 22-26) to document the optional `lfo` field and the v1.0/v1.1 acceptance.

---

### `apollo/synth/render.py` (service, streaming/file-I/O)

**Analog:** itself. The poly param-by-index landmine is already solved; the new sliders ride the same resolution path.

**Runtime name→index resolution** (the load-bearing landmine fix — `_build_name_index_map` lines 77-97): resolves Faust slider NAME → int index from `synth.get_parameters_description()`, matching on the `label` field (with a trailing-path-segment fallback). The LFO sliders `lfo_rate`/`lfo_depth`/`lfo_wave` resolve through this **unchanged** — RESEARCH verified they resolve cleanly by `label` (Pitfall 3). Do NOT add a static index map.

**Per-op slider-set loop pattern** (lines 135-145) — the existing loop guards each slider name and sets by int index:
```python
name_to_index = _build_name_index_map(synth)
for i, op in enumerate(params.operators, start=1):
    for field in _OP_SLIDER_FIELDS:
        slider = f"op{i}_{field}"
        if slider not in name_to_index:
            raise IngestError(pair_path, f"render engine is missing expected param {slider!r}")
        synth.set_parameter(int(name_to_index[slider]), float(getattr(op, field)))
```

**LFO extension** (mirror that loop exactly; place after the per-op loop, guard on `params.lfo is not None` so the no-lfo patch never looks up absent sliders — Pitfall 3):
```python
if params.lfo is not None:
    for slider, val in (("lfo_rate", params.lfo.rate),
                        ("lfo_depth", params.lfo.depth),
                        ("lfo_wave", float(params.lfo.wave))):
        if slider not in name_to_index:
            raise IngestError(pair_path, f"render engine is missing expected param {slider!r}")
        synth.set_parameter(int(name_to_index[slider]), float(val))
```
Note: `lfo.target` is NOT a runtime slider — it selects the DSP wiring branch in `dsp_string` at compile time (like algorithm), so it is not set here. Keep `_OP_SLIDER_FIELDS` (line 74) unchanged. Determinism + normalization (`_normalize_peak` lines 168-179) handle LFO peak changes already (RESEARCH Pitfall 5) — no change.

---

### `tests/test_synth_render.py` (test)

**Analog:** itself. Mirror existing helpers and add LFO variants.

**Helper-kwarg pattern** — extend `_fm_params` (lines 62-68) and `_manifest_dict` (lines 71-82) with an optional `lfo=` kwarg (Wave-0 gap, RESEARCH line 332). Both currently pop `algorithm`/`gain` from kwargs and build 3 identical ops; add the same pop-and-thread for `lfo`. `_manifest_dict` should also allow overriding `spec_version` (currently hardcoded `"1.0"` line 78) so v1.1 fixtures can be built.

**Determinism test pattern** (mirror `test_render_deterministic` lines 97-105): new `test_lfo_render_deterministic` — `np.array_equal(render(lfo_params,...), render(lfo_params,...))` (RESEARCH verified feasible).

**Bit-identity / backward-compat tests** (new):
- `test_lfo_absent_bit_identical` — render a no-lfo params twice, `np.array_equal`; AND assert `dsp_string(no_lfo)` equals the v1.0 string (no committed `.wav` fixture — matches in-process convention, RESEARCH line 333).
- `test_lfo_depth0_matches_static` — `np.array_equal` between depth-0 lfo render and static render (RESEARCH verified max diff 0.0).

**Mel time-variation test** (mirror `test_timbre_discriminable` lines 130-150, which already computes `cos`/`l2` through `MelExtractor` and asserts `cos < 0.999`): new `test_lfo_time_varies` — LFO mel vs depth-0 mel, assert `cos < 0.999` at a clear rate (6 Hz — RESEARCH measured cos=0.999/L2=74; do NOT use the 0.05 Hz edge, Pitfall 4).

**Mel-contract / no-clip extensions** (mirror `test_mel_contract` lines 117-127 and `test_no_clipping` lines 108-114): extend with an lfo patch — assert `(96,128)` float32 and `max abs ≤ 1.0` hold (RESEARCH verified).

**Manifest-validation tests** (mirror the always-run block lines 172-211, which use `pytest.raises(IngestError, match=...)` and a per-test mutated `_manifest_dict()`):
- `test_manifest_accepts_v11` — a valid v1.1 manifest loads (keep `test_manifest_bad_version` for `"9.9"`).
- `test_lfo_requires_v11` — `spec_version "1.0"` + lfo block → `pytest.raises(IngestError, match="1.1")`.
- `test_lfo_rate_out_of_range`, `test_lfo_wave_bad_enum`, `test_lfo_nan` — mirror `test_manifest_ratio_out_of_range` (lines 192-199) and `test_manifest_nan_field` (lines 202-211).

These validation tests need no dawdreamer (they call `load_manifest` directly), so place them in the always-run section below the importorskip (lines 164-211).

---

### `data/pairs/CORPUS-CONVENTIONS.md` (docs)

**Analog:** itself — the `call_fm.json` schema section (lines 37-65).

**Schema-section pattern** (lines 37-65): a JSON example block followed by a field table (`| Field | Type | Range | Notes |`). Extend by:
- Updating the heading (line 37) and the `spec_version` row (line 56) to note `"1.0"` OR `"1.1"`; lfo requires `"1.1"`.
- Adding an optional `lfo` block to the JSON example (mirror RESEARCH Manifest Schema, lines 270-282).
- Adding rows for `lfo.rate` `[0.05,20.0]`, `lfo.depth` `[0.0,1.0]`, `lfo.wave` `{0,1,2}` sine/triangle/square, `lfo.target` `{0,1}` level/pitch (RESEARCH field table lines 285-290).
- Documenting for Phase-5 parity (RESEARCH Open Question 3): the unipolar tremolo formula `lvl_mod = 1 - depth*(1-unipolar)` and the vibrato formula `pow(2, lfo_bi*depth*maxcents/1200)`, plus the "low rate ⇒ slow partial sweep over the 0.5–1.5 s gesture" note (Pitfall 4).

## Shared Patterns

### Numeric-only DSP-string security boundary
**Source:** `apollo/synth/spec.py` header (lines 24-27), `dsp_string` docstring (lines 105-106), float substitution `{float(x):.6f}` (lines 134-143).
**Apply to:** `spec.py` LFO wiring. Waveform/target selection is by validated **integer** via Faust `select3(int(lfo_wave), ...)`; rate/depth are validated **floats** formatted `:.6f`. NO manifest string ever reaches the DSP source (T-06-01 class).

### Fail-loud IngestError(pair_path, reason)
**Source:** `apollo/synth/manifest.py` `_check_number` (lines 64-77), algorithm guard (lines 104-109), version guard (lines 95-101).
**Apply to:** all new lfo validation in `manifest.py` and the missing-slider guard in `render.py` (lines 141-144). Every rejection names the pair via `pair_path` as the FIRST arg and a `{label} ...` reason.

### Runtime label-based param resolution (poly landmine)
**Source:** `apollo/synth/render.py` `_build_name_index_map` (lines 77-97) + per-op set loop (lines 135-145).
**Apply to:** setting `lfo_rate`/`lfo_depth`/`lfo_wave`. Resolve by `label`, set by `int` index, guard each name, guard the whole block on `params.lfo is not None`.

### In-process pytest helpers + importorskip guard
**Source:** `tests/test_synth_render.py` — `_fm_params`/`_manifest_dict`/`_write_manifest` (lines 62-86), `pytest.importorskip("dawdreamer")` (line 91), `pytest.raises(IngestError, match=...)` validation tests (lines 172-211).
**Apply to:** all new LFO tests. No committed `.wav` fixtures; render in-process to `tmp_path`; render tests under the importorskip, validation tests in the always-run section.

## No Analog Found

None. Every Phase-7 file is an extension of an existing Phase-6 file with a strong in-repo analog (its own current structure).

## Metadata

**Analog search scope:** `apollo/synth/` (spec.py, manifest.py, render.py), `tests/test_synth_render.py`, `data/pairs/CORPUS-CONVENTIONS.md`
**Files scanned:** 5 (all read in full this session)
**Pattern extraction date:** 2026-06-02

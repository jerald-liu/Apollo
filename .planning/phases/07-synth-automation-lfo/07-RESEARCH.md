# Phase 7: Synth Automation (LFO) - Research

**Researched:** 2026-06-02
**Domain:** Faust LFO synthesis under DawDreamer polyphony; deterministic spec versioning; untrusted-manifest validation
**Confidence:** HIGH (core determinism/backward-compat/waveform/target claims empirically validated in `.venv` against `dawdreamer==0.8.3` this session)

## Summary

Phase 7 adds one optional global LFO to the owned 3-op FM synth, bumping `SPEC_VERSION` 1.0 → 1.1. The LFO is an optional `lfo` block in `call_fm.json`; absent ⇒ no modulation, and the render is **bit-identical** to Phase 6 output. Every hard claim below was checked empirically with DawDreamer in this session (not just from training data), because the determinism guarantee is the whole point of the phase.

**Headline empirical findings (this session, `.venv/bin/python` + `dawdreamer==0.8.3`):**
- **The "always-wire, depth=0" backward-compat approach is bit-identical to the unmodulated patch** — `np.array_equal(static, lfo_depth0) == True`, max abs diff `0.0`. This is the cleanest backward-compat mechanism *for the v1.1 audio*, BUT it does **not** by itself preserve bit-identity against the *Phase-6-emitted DSP string* unless the v1.0 string is emitted unchanged when `lfo` is absent. See Pitfall 1 — recommendation is "emit v1.0 string verbatim when no lfo," which is strictly safer.
- **LFO render is deterministic across runs** — `np.array_equal(run1, run2) == True` for level and pitch targets, single-note and the 3-note Apollo gesture.
- **LFO phase is per-voice / onset-relative, not global transport time** — rendering the same note at `start=0.0` vs `start=0.17s` and onset-aligning gives max diff `0.0`. `os.osc` inside the poly voice resets at note-on, so phase starts deterministically at 0 each note. The spike's "global-time" worry does **not** materialize for note-triggered voices.
- **Waveform select by integer is feasible with zero string injection** — Faust `select3(int(lfo_wave), os.osc, os.lf_triangle, os.lf_squarewave)` driven by a numeric `lfo_wave` hslider; sine vs square produce different audio. No manifest string ever touches the DSP source.
- **Both targets work:** operator LEVEL (tremolo) and carrier PITCH (vibrato via `pow(2, cents/1200)`) both render deterministically and differ from depth=0.
- **Time-variation is measurable through the frozen `(96,128)` MelExtractor** — LFO render vs depth=0 render gave `cos=0.9990, L2=74.11` (tremolo sidebands shift the mel). A `cos < 0.999` assertion is a robust, contract-safe time-variation test.

**Primary recommendation:** ONE global LFO block; waveform enum int `{0:sine, 1:triangle, 2:square}`; targets = a small fixed enum `{0:operator level (tremolo), 1:carrier pitch (vibrato)}`; rate 0.05–20 Hz, depth 0–1. For backward-compat, **emit the exact Phase-6 v1.0 DSP string when `lfo` is absent** (don't rely on depth=0 wiring for the no-LFO case), and additionally keep depth=0 wiring bit-clean for authored-but-disabled LFOs. Accept `spec_version ∈ {"1.0","1.1"}`; a `"1.0"` manifest carrying an `lfo` block is **rejected** (lfo requires 1.1).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| LFO schema + ranges + waveform/target enums | `apollo/synth/spec.py` (versioned source of truth) | — | Single place the spec lives; Phase 5 browser synth mirrors it (SC#4) |
| LFO → Faust DSP wiring | `apollo/synth/spec.py::dsp_string` | — | The ONLY place a Faust patch is constructed; numeric-only security boundary |
| LFO manifest validation (untrusted input) | `apollo/synth/manifest.py::load_manifest` | — | Fail-loud trust boundary (T-06-01 class) |
| LFO runtime param set by index | `apollo/synth/render.py` (`_build_name_index_map`) | — | Poly param-by-index landmine already handled; new sliders resolve by `label` |
| Determinism / bit-identity guarantee | `spec.py` (string) + `render.py` (engine consts) | tests | Engine consts + DSP source fully determine the render |
| Browser-synth parity | Phase 5 (out of scope here) | docs (`CORPUS-CONVENTIONS.md`) | Phase 7 only documents the schema for Phase 5 to consume |

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SYNTH-01 | Optional per-patch LFO (rate, depth, waveform, target) in `call_fm.json`, rendered deterministically; spec → v1.1; v1.0 manifest renders bit-identically; loader accepts both versions; mel contract unchanged; documented for Phase 5 | Faust idioms (§Architecture Patterns), determinism + per-voice phase (§Validation Architecture, empirically validated), backward-compat mechanism (§Pitfall 1), manifest schema + validation (§Manifest Schema), mel time-variation test (§Validation Architecture) |

## Standard Stack

No new dependencies. Phase 7 extends three existing owned modules.

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| dawdreamer | 0.8.3 | Headless Faust render engine (already a dep, A4 cleared in 06-01) | [VERIFIED: imports cleanly in project `.venv`, arm64/Py3.11, this session] |
| Faust `stdfaust.lib` (`os.*`) | bundled w/ dawdreamer | LFO oscillators | [VERIFIED: `os.osc`, `os.lf_triangle`, `os.lf_squarewave`, `select3` all compile + render this session] |

### Faust LFO primitives (verified this session)
| Primitive | Output | Use | Notes |
|-----------|--------|-----|-------|
| `os.osc(rate)` | bipolar sine [-1,1] | waveform 0 (sine) | [VERIFIED] phase starts at 0 per voice |
| `os.lf_triangle(rate)` | bipolar triangle [-1,1] | waveform 1 (triangle) | [VERIFIED] low-frequency (anti-aliased not required at LFO rates) |
| `os.lf_squarewave(rate)` | bipolar square [-1,1] | waveform 2 (square) | [VERIFIED] hard edges; fine for sub-audio modulation |
| `select3(int(sel), a, b, c)` | one of 3 | waveform selection by **numeric** index | [VERIFIED] `int(lfo_wave)` keeps it numeric — no string injection |

**Do NOT use** `os.lf_saw` for v1 (not in the agreed `{sine, triangle, square}` set; reserve the index space for it later). [ASSUMED: it exists and would work, but out of scope.]

**Installation:** none — `dawdreamer==0.8.3` already in `.venv` (06-01).

**Version verification:** `dawdreamer` has no `__version__` (spike landmine); pin stays `0.8.3` from `pyproject.toml`. Faust lib version is whatever ships in the wheel — do not assume newer `os.*` helpers exist beyond the four verified above.

## Architecture Patterns

### System Architecture Diagram

```
call_fm.json (v1.0 OR v1.1, untrusted on-disk)
        │
        ▼
load_manifest  ──reject──►  IngestError(pair_path, reason)   [fail-loud trust boundary]
  • version ∈ {"1.0","1.1"}
  • if lfo present ⇒ version must be "1.1"
  • lfo numeric/finite/range/enum checks
        │ FmParams(+ optional LfoParams)
        ▼
dsp_string(p)  [ONLY place Faust source is built; NUMERIC-only]
  • lfo absent ⇒ emit EXACT Phase-6 v1.0 string  ──► bit-identical to Phase 6
  • lfo present ⇒ emit v1.0 body + LFO block:
        lfo_rate/lfo_depth/lfo_wave hsliders (numeric)
        lfo_bi = select3(int(lfo_wave), os.osc, os.lf_triangle, os.lf_squarewave)
        target=level: multiply carrier(s) by (1 - depth*(1-unipolar))
        target=pitch: multiply carrier freq by pow(2, lfo_bi*depth*maxcents/1200)
        │ DSP source string
        ▼
render()  [DawDreamer, num_voices=8, BLOCK=512, SR=44100]
  • _build_name_index_map: resolve lfo_rate/lfo_depth/lfo_wave by label → int index
  • set_parameter(int idx, float val)   [poly param-by-index landmine handled]
  • LFO os.osc phase resets per voice at note-on  ──► deterministic, onset-relative
        │ mono float32 audio
        ▼
_normalize_peak (TARGET_PEAK=0.89; silence floor) ──► (frozen) MelExtractor (96,128)
```

### Pattern 1: LFO as an optional FmParams field
**What:** Add `lfo: LfoParams | None = None` to `FmParams` (keep the dataclass frozen/hashable — `LfoParams` itself frozen). Absent (`None`) ⇒ no modulation.
**When to use:** Always — this is the schema shape SYNTH-01 mandates.
**Example:**
```python
# Source: extends apollo/synth/spec.py (this phase)
from enum import IntEnum

class LfoWave(IntEnum):
    SINE = 0
    TRIANGLE = 1
    SQUARE = 2

class LfoTarget(IntEnum):
    LEVEL = 0   # tremolo / timbre motion (scales carrier output)
    PITCH = 1   # vibrato (scales carrier frequency in cents)

@dataclass(frozen=True)
class LfoParams:
    rate: float       # Hz, [0.05, 20.0]
    depth: float      # [0.0, 1.0]
    wave: int         # LfoWave value
    target: int       # LfoTarget value

@dataclass(frozen=True)
class FmParams:
    algorithm: int
    operators: tuple[OperatorParams, ...]
    gain: float
    lfo: LfoParams | None = None   # optional; None ⇒ Phase-6 identical render
```

### Pattern 2: Backward-compat by emitting the v1.0 string verbatim when lfo is absent
**What:** In `dsp_string`, branch at the top: `if p.lfo is None: return <exact existing v1.0 body>`. Only when `lfo` is present do you wire the LFO block.
**When to use:** This is the recommended backward-compat mechanism (see Pitfall 1 — strictly safer than "always wire depth=0").
**Example (LFO block, verified to compile + render this session):**
```faust
// Source: validated in /tmp/lfo_probe.py this session (dawdreamer 0.8.3)
lfo_rate  = hslider("lfo_rate",  6.0, 0.05, 20, 0.001);
lfo_depth = hslider("lfo_depth", 0.0, 0,    1,  0.001);
lfo_wave  = hslider("lfo_wave",  0,   0,    2,  1);
lfo_bi = select3(int(lfo_wave),
                 os.osc(lfo_rate),
                 os.lf_triangle(lfo_rate),
                 os.lf_squarewave(lfo_rate));   // bipolar [-1,1], phase starts at 0 per voice
// target = LEVEL (tremolo): unipolar gain in [1-depth, 1]
lfo_uni = (lfo_bi + 1.0) / 2.0;
lvl_mod = 1.0 - lfo_depth * (1.0 - lfo_uni);
// applied to each carrier: ... * lvl_mod
// target = PITCH (vibrato): +/- depth*maxcents cents (maxcents baked literal, e.g. 50 or 100)
// pitch_mul = pow(2.0, (lfo_bi * lfo_depth * 100.0) / 1200.0);
// applied to carrier osc freq: os.osc(freq * opN_ratio * pitch_mul + mod)
```

### Pattern 3: Targeting under the three existing algorithm templates
**What:** The LFO target must be applied at the **carrier** of each topology, not blindly. The existing templates name their carriers explicitly:
- STACK: single carrier `car` (op1).
- PARALLEL_MODS: single carrier `car` (op1).
- CARRIER_PAIR: two carriers `car1` (op1) and `car2` (op2 additive).

| Target | STACK / PARALLEL_MODS | CARRIER_PAIR |
|--------|------------------------|--------------|
| LEVEL (tremolo) | multiply `car` by `lvl_mod` | multiply both `car1` and `car2` by `lvl_mod` (global LFO ⇒ both move together) |
| PITCH (vibrato) | multiply carrier `os.osc` freq arg by `pitch_mul` | multiply each carrier's freq arg by `pitch_mul` |

**Recommendation:** For the v1.1 minimal slice, apply the global LFO to **all carriers uniformly** (it's one global LFO per patch, not per-op). This keeps the wiring symmetric across the three templates and avoids a per-op LFO addressing scheme (deferred). Modulators are left unmodulated by the LFO in v1.1.

### Anti-Patterns to Avoid
- **Interpolating any manifest string into the DSP source.** Waveform/target selection is by validated integer only (`select3(int(...))`). [security boundary — same numeric-only rule as Phase 6, T-06-01 class]
- **Targeting FM modulation depth/index in v1.1.** Cheap to add later (multiply a modulator's `* level * freq` term by `lvl_mod`), but it is a *third* target and widens scope — recommend deferring to keep the target enum at `{level, pitch}`. [ASSUMED feasibility — not validated this session; the wiring is trivial but the musical/mel behavior was not measured.]
- **Relying on `os.phasor` + manual phase math.** `os.osc`/`os.lf_*` already start at phase 0 per voice (verified); hand-rolling phase accumulation adds a determinism surface for no benefit.
- **Per-op or multi-LFO schema in v1.1.** One global LFO only — reserve enum/array space but do not implement.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| LFO oscillator | custom phasor + sin/tri/sqr math | `os.osc` / `os.lf_triangle` / `os.lf_squarewave` | Faust primitives are band-appropriate, phase-0 per voice, verified deterministic |
| Waveform dispatch | Python `if wave==0: dsp+="os.osc"...` (string injection!) | Faust `select3(int(lfo_wave), ...)` | Keeps DSP source static + numeric-only (security) |
| Per-note LFO phase reset | manual gate-driven phase reset | DawDreamer poly voice allocation | [VERIFIED] voice osc already resets at note-on; onset-aligned diff = 0.0 |
| Cents→ratio conversion | lookup tables | `pow(2.0, cents/1200.0)` in Faust | One-line, exact, deterministic |

**Key insight:** Faust's `os.*` LFOs under DawDreamer polyphony already give the exact determinism guarantee Phase 7 needs (phase-0 per voice, bit-identical re-render). The work is *schema + validation + wiring*, not DSP invention.

## Runtime State Inventory

> This is a spec-versioning / additive-feature phase, not a rename. Inventory is light but real (the bit-identity guarantee depends on no stale state).

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | Existing authored corpus `call_fm.json` files are all `spec_version "1.0"` with no `lfo` block. They MUST continue to render bit-identically. | Code: emit v1.0 DSP string verbatim when `lfo` absent (Pitfall 1). No data migration — v1.0 manifests are valid as-is under v1.1 loader. |
| Live service config | None — renderer is in-process, no external service. | None. |
| OS-registered state | None. | None. |
| Secrets/env vars | None — manifests carry numbers only. | None. |
| Build artifacts | `apollo/synth/spec.py::SPEC_VERSION` is written into every newly-generated manifest; rendered `call.wav` is gitignored (06-03) so no stale audio is committed. Existing `.wav` on disk for any authored pair will be **regenerated** by `render_corpus` and must remain byte-identical for no-lfo pairs. | Verify: a no-lfo pair re-rendered under v1.1 code produces a `call.wav` byte-identical to the Phase-6 render (regression test). |

**Canonical question — after the spec bumps to 1.1, what still references "1.0"?** The `load_manifest` version guard (must now accept both), test fixtures that assert `"1.0"` rejection of unknown versions (still valid — `"9.9"` still rejected), and `CORPUS-CONVENTIONS.md` (documents the schema — must gain the `lfo` block + version note).

## Common Pitfalls

### Pitfall 1: "Always-wire depth=0" is bit-identical to v1.1-static but NOT necessarily to Phase-6 DSP
**What goes wrong:** You wire the LFO block unconditionally with `depth=0` for no-lfo manifests, assuming it reproduces Phase 6. It reproduces *a depth-0 v1.1 render* (verified `np.array_equal == True` vs a depth-0 v1.1 patch), but the emitted DSP source is now different from the Phase-6 source string. Any future change to the LFO block, or a Faust codegen difference from the extra (even if multiply-by-1) ops, risks a non-bit-identical regression against the already-authored corpus.
**Why it happens:** Conflating "depth=0 audio looks identical" with "DSP source is identical." The bit-identity guarantee in SYNTH-01 SC#2 is against *Phase 6 output*, which is most robustly preserved by emitting the *same source*.
**How to avoid:** Two-layer defense — (1) `if p.lfo is None: return <exact Phase-6 v1.0 body>` (recommended primary mechanism); (2) additionally, prove `depth=0` wiring is bit-clean so an authored-but-disabled LFO doesn't surprise the author. This session verified (2) holds today (`max abs diff 0.0`); the regression test should pin both.
**Warning signs:** A no-lfo pair's `call.wav` byte hash changes after the Phase-7 merge.

### Pitfall 2: Assuming LFO uses global transport time (the spike's poly worry)
**What goes wrong:** You add an LFO and fear that because the 3 notes start at 0.0/0.5/1.0s, each note sees a different LFO phase (global time), making re-renders order-dependent or "smeared."
**Why it happens:** Reasonable extrapolation from the spike's poly-param landmine.
**How to avoid:** It does NOT happen — [VERIFIED this session] `os.osc` inside the poly voice resets at note-on; onset-aligned renders at start=0.0 vs 0.17s vs 0.3s gave max diff `0.0`. Each note's LFO starts at phase 0. Re-render is bit-identical. No special handling needed.
**Warning signs:** None observed; if a future Faust/DawDreamer upgrade changed voice-reset behavior, the determinism test would catch it.

### Pitfall 3: New LFO sliders break the param-index map silently
**What goes wrong:** `lfo_rate`/`lfo_depth`/`lfo_wave` are added but `render.py` only sets `op{i}_ratio`/`op{i}_level`, so the LFO sliders sit at their hslider defaults (or, worse, an index shift mis-sets an operator).
**Why it happens:** `_build_name_index_map` resolves by `label`; new sliders must be added to the set-by-index loop. Indices are assigned by Faust declaration order and shift as the patch grows (spike note).
**How to avoid:** Add LFO sliders to the runtime set loop, resolved by label exactly like `op{i}_*` (verified: `lfo_rate`/`lfo_depth`/`lfo_wave` resolve cleanly by label this session). Only set them **when `p.lfo is not None`** (when absent the sliders aren't emitted at all, so the map won't contain them — guard the lookup).
**Warning signs:** `IngestError "render engine is missing expected param 'lfo_rate'"` if you try to set them on a no-lfo patch.

### Pitfall 4: Short call.mid means low rates yield only a partial sweep
**What goes wrong:** A 0.05 Hz LFO over a 0.5–1.5 s gesture completes <8% of a cycle — barely any motion — and a time-variation test might fail at very low rates.
**Why it happens:** `call.mid` is 0.5–1.5 s by design (monophonic tiny gestures).
**How to avoid:** This is intended expressive behavior (partial sweep). For the *time-variation regression test*, use a clearly-audible rate (e.g. 6 Hz, as validated: `cos=0.999, L2=74`), not a 0.05 Hz edge case. Document in `CORPUS-CONVENTIONS.md` that low rates give slow drift over the gesture.
**Warning signs:** A flaky time-variation test that passes at 6 Hz but fails at 0.1 Hz — pin the test rate.

### Pitfall 5: Square-wave / hard-edge depth at high rate could push peaks
**What goes wrong:** Square-wave tremolo or deep vibrato changes the peak amplitude; since `_normalize_peak` is post-render scalar gain, this is fine for clipping — but a depth-driven peak change alters the normalization scalar, which is still deterministic (so OK).
**Why it happens:** Modulation changes the waveform's peak.
**How to avoid:** Nothing required — `_normalize_peak` already handles it deterministically (verified no-clip + bit-identical with LFO). Just confirm `test_no_clipping` still passes for an LFO patch.
**Warning signs:** None — normalization is linear and deterministic.

## Code Examples

### Validating an lfo block in load_manifest (mirrors _check_number discipline)
```python
# Source: extends apollo/synth/manifest.py (this phase)
LFO_RATE_MIN, LFO_RATE_MAX = 0.05, 20.0
LFO_DEPTH_MIN, LFO_DEPTH_MAX = 0.0, 1.0

def _check_enum_int(value, pair_path, label, valid: set[int]) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise IngestError(pair_path, f"{label} must be an int, got {type(value).__name__}")
    if value not in valid:
        raise IngestError(pair_path, f"{label} {value} not in {sorted(valid)}")
    return value

# inside load_manifest, after gain:
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
Note: `_check_number` already rejects missing keys via `.get()` returning `None` → `not isinstance(None, (int,float))` → IngestError. Confirm the message names the pair (it does — `pair_path` first arg).

### Setting LFO params by index at runtime (extends render.py)
```python
# Source: extends apollo/synth/render.py (this phase)
# after the per-operator set loop:
if params.lfo is not None:
    for slider, val in (("lfo_rate", params.lfo.rate),
                        ("lfo_depth", params.lfo.depth),
                        ("lfo_wave", float(params.lfo.wave))):
        if slider not in name_to_index:
            raise IngestError(pair_path, f"render engine is missing expected param {slider!r}")
        synth.set_parameter(int(name_to_index[slider]), float(val))
```

## Manifest Schema (v1.1)

```jsonc
{
  "spec_version": "1.1",          // "1.0" or "1.1"; lfo REQUIRES "1.1"
  "algorithm": 0,
  "operators": [ /* exactly 3, unchanged from v1.0 */ ],
  "gain": 0.5,
  "lfo": {                         // OPTIONAL; omit ⇒ bit-identical to Phase 6
    "rate": 6.0,                   // Hz, [0.05, 20.0]
    "depth": 0.8,                  // [0.0, 1.0]
    "wave": 0,                     // 0=sine, 1=triangle, 2=square
    "target": 0                    // 0=level (tremolo), 1=pitch (vibrato)
  }
}
```

| Field | Type | Range / Enum | Notes |
|-------|------|--------------|-------|
| `lfo.rate` | number | [0.05, 20.0] Hz | low rates = slow partial sweep over the 0.5–1.5 s gesture |
| `lfo.depth` | number | [0.0, 1.0] | 0 ⇒ no audible modulation (and bit-identical to depth-0 wiring) |
| `lfo.wave` | int | {0,1,2} | sine/triangle/square; reserve 3=saw for later |
| `lfo.target` | int | {0,1} | level/pitch; reserve 2=FM-mod-depth for later |

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `SPEC_VERSION = "1.0"`, single accepted version | `SPEC_VERSION = "1.1"`, loader accepts `{"1.0","1.1"}` | This phase | v1.0 corpus still valid; new pairs may use lfo |
| `FmParams` = algorithm + ops + gain (static patch) | `FmParams` + optional `lfo` | This phase | Time-varying timbre/pitch |
| `dsp_string` always emits static body | `dsp_string` branches: v1.0 body if no lfo, else +LFO block | This phase | Bit-identity preserved for no-lfo |

**Deprecated/outdated:** Nothing removed. The v1.0 manifest format remains a first-class, accepted input (subset of v1.1).

## Validation Architecture

> `workflow.nyquist_validation` is `false` in config, so this section is advisory — but the determinism/backward-compat claims are exactly what the phase must prove, so the test map below should drive the plan's verification steps. Framework is the existing `pytest` suite (`tests/test_synth_render.py`, 177 tests passing).

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing) |
| Config file | none custom — repo root; dawdreamer-render tests guarded by `pytest.importorskip("dawdreamer")` |
| Quick run command | `.venv/bin/python -m pytest tests/test_synth_render.py -q` |
| Full suite command | `.venv/bin/python -m pytest -q` |

### Phase Requirements → Test Map
| Req | Behavior | Test Type | Command | Exists? |
|-----|----------|-----------|---------|---------|
| SYNTH-01 | No-lfo v1.1 manifest renders bit-identically to Phase 6 (no-lfo) | regression | new `test_lfo_absent_bit_identical` — render same manifest with v1.0-string path; `np.array_equal` | ❌ new |
| SYNTH-01 | LFO render is deterministic across runs | unit | new `test_lfo_render_deterministic` — `np.array_equal(a,b)` | ❌ new (mirror `test_render_deterministic`) [VERIFIED feasible this session] |
| SYNTH-01 | LFO produces measurable time-variation vs static | unit | new `test_lfo_time_varies` — LFO mel vs depth-0 mel, `cos < 0.999` | ❌ new [VERIFIED cos=0.999/L2=74 this session @6Hz] |
| SYNTH-01 | depth=0 LFO render == static render (bit) | unit | new `test_lfo_depth0_matches_static` — `np.array_equal` | ❌ new [VERIFIED max diff 0.0 this session] |
| SYNTH-01 | loader accepts "1.0" AND "1.1" | unit | new `test_manifest_accepts_v11` + keep `test_manifest_bad_version` ("9.9" rejected) | partial (bad_version exists) |
| SYNTH-01 | lfo on a "1.0" manifest is rejected | unit | new `test_lfo_requires_v11` — `pytest.raises(IngestError, match="1.1")` | ❌ new |
| SYNTH-01 | lfo field validation (range/enum/finite/bool) | unit | new `test_lfo_rate_out_of_range`, `test_lfo_wave_bad_enum`, `test_lfo_nan` | ❌ new (mirror existing manifest tests) |
| SYNTH-01 | no-clip holds with LFO | unit | extend `test_no_clipping` with an lfo patch | ❌ extend [VERIFIED no-clip this session] |
| SYNTH-01 | mel contract `(96,128)` holds with LFO | unit | extend `test_mel_contract` with an lfo patch | ❌ extend [VERIFIED this session] |

### Sampling Rate
- **Per task commit:** `.venv/bin/python -m pytest tests/test_synth_render.py -q`
- **Per phase gate:** full suite green (`.venv/bin/python -m pytest -q`)

### Wave 0 Gaps
- [ ] Test helpers in `tests/test_synth_render.py` need an `lfo=` kwarg in `_fm_params` / `_manifest_dict` (currently no lfo support).
- [ ] A "Phase-6 golden" reference for bit-identity: simplest is to assert `np.array_equal(render(no_lfo_params), render(no_lfo_params))` AND that the emitted `dsp_string(no_lfo)` equals the v1.0 string — no committed `.wav` fixture needed (in-process, matches existing convention).

## Security Domain

> The `lfo` block is part of the untrusted-manifest trust boundary (T-06-01 class). Same numeric-only DSP rule as Phase 6.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | yes | `load_manifest` type/finite/range/enum checks on every lfo field; reject bools, NaN/Inf, out-of-range, unknown enum ints (mirror `_check_number`) |
| V2/V3/V4/V6 | no | No auth/session/access-control/crypto surface in a local render pipeline |

### Known Threat Patterns
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Faust DSP source injection via manifest string | Tampering | NO manifest string ever interpolated; `lfo.wave`/`target` are validated **ints** routed through Faust `select3(int(...))`; `rate`/`depth` are validated **floats** formatted with `:.6f` into static slider declarations [VERIFIED numeric-only path renders this session] |
| Out-of-range / NaN / Inf lfo values | Tampering | `_check_number` finite + range check; `_check_enum_int` for wave/target; IngestError names the pair |
| Version downgrade carrying lfo (v1.0 + lfo) | Tampering / spec confusion | Reject `lfo` block unless `spec_version == "1.1"` |
| DoS via extreme rate | DoS | rate capped at 20 Hz; render duration cap (`MAX_RENDER_SECONDS`) unchanged — LFO does not extend render length |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Default `maxcents` for vibrato (e.g. 50 or 100 cents at depth=1) is a reasonable musical range — the exact literal is a discuss-phase decision | Pattern 2 | Low — any baked literal is deterministic; only the musical feel changes. Lock the value in discuss/plan. |
| A2 | Targeting FM modulation depth (3rd target) is "cheap to add" — wiring is trivial but musical/mel behavior NOT measured this session | Anti-Patterns | Low (it's deferred); if promoted later, validate mel behavior empirically |
| A3 | `os.lf_saw` exists in the bundled Faust lib (reserved enum 3) | Standard Stack | Low — out of scope for v1.1; verify before implementing saw |
| A4 | Applying the global LFO to ALL carriers uniformly (incl. both CARRIER_PAIR carriers) is the desired musical behavior | Pattern 3 | Medium — alternative is "first carrier only." A musical/scope decision for discuss-phase. Default = all carriers (symmetric). |
| A5 | A `cos < 0.999` mel threshold reliably separates LFO-on from static at the chosen test rate (6 Hz) | Validation Architecture | Low — measured cos=0.9990 at 6 Hz; keep test rate ≥ a few Hz, don't test the 0.05 Hz edge |

## Open Questions

1. **Exact vibrato cent range and whether pitch target is in the v1.1 minimal slice.**
   - What we know: pitch (vibrato) renders deterministically and differs from static [VERIFIED].
   - What's unclear: whether v1.1 ships both `{level, pitch}` or only `level` for the truly-minimal slice; and the max-cents literal.
   - Recommendation: ship both targets (both validated, marginal cost) with `maxcents` locked in discuss-phase (suggest 50 cents for musical vibrato, 100 for dramatic). If scope must shrink, ship `level` only and reserve `target=1`.

2. **CARRIER_PAIR LFO application (A4).**
   - What we know: one global LFO; CARRIER_PAIR has two carriers.
   - What's unclear: modulate both carriers or just `car1`.
   - Recommendation: both, uniformly (symmetric, simplest). Confirm in discuss-phase.

3. **Browser-synth parity scope (Phase 5).**
   - What we know: Phase 7 only documents the LFO schema; Phase 5 implements the Web Audio mirror.
   - What's unclear: nothing blocking — `CORPUS-CONVENTIONS.md` + the versioned `spec.py` enums are the contract Phase 5 consumes.
   - Recommendation: document the four lfo fields + waveform/target enums + the unipolar tremolo formula and the `pow(2, cents/1200)` vibrato formula so Phase 5 can match math exactly.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| dawdreamer | render + render-tests | ✓ | 0.8.3 | tests `importorskip` on non-arm64 CI |
| Faust `stdfaust.lib` os.* | LFO oscillators | ✓ | bundled in wheel | — (verified `os.osc`/`os.lf_triangle`/`os.lf_squarewave`/`select3`/`pow` all compile) |
| MelExtractor (torch/torchaudio) | mel-contract test | ✓ | project `.venv` | — |

**Missing dependencies:** none. (gsd-sdk absent per environment note, not needed for this phase.)

## Project Constraints (from CLAUDE.md)

- **Just-notes vocab, extensible by design** — LFO is a *synth* feature (call-side timbre), not a vocab/token change; it does not touch the tokenizer. Reserve enum space (saw waveform, FM-mod target) without implementing.
- **Mel-condition the call** — LFO motion must remain visible to MelExtractor; verified it is (cos=0.999 vs static). Keep the `(96,128)` contract frozen.
- **Monophonic + tiny gestures (0.5–1.5 s)** — low LFO rates give partial sweeps; this is intended, document it. Don't widen gesture scope.
- **Local-only** — render is in-process; no cloud.
- **Graphite stack discipline** — Phase 7 is one coherent change (LFO); keep it on its own stacked branch; restack after trunk updates; merge stacks to `main`.

## Sources

### Primary (HIGH confidence)
- **Empirical validation this session** — `dawdreamer==0.8.3` in project `.venv` (`/tmp/lfo_probe*.py`): depth-0 bit-identity (`array_equal True`, max diff 0.0), cross-run determinism, per-voice/onset-relative LFO phase (onset-aligned diff 0.0 at 0.17s and 0.3s offsets), waveform-by-int select, level+pitch targets render+differ, multi-note gesture determinism, LFO-vs-static mel `cos=0.9990/L2=74.11`, no-clip with LFO.
- `apollo/synth/spec.py`, `manifest.py`, `render.py`, `tests/test_synth_render.py` — current Phase-6 contracts (read this session).
- `.claude/skills/spike-findings-apollo/references/synth-independent-rendering.md` — poly param-by-index landmine, benign `undefined symbol: effect` warning, clip/headroom, no `dawdreamer.__version__`.
- `.planning/STATE.md` 06-01/06-02/06-03 decisions — slider naming, label-based index resolution, ADSR-as-literals, single render path.

### Secondary (MEDIUM confidence)
- Faust `stdfaust.lib` oscillator semantics (`os.osc` phase-0, `os.lf_*` low-freq waveforms) — behavior confirmed empirically; library-doc cross-check not separately fetched (Context7/web not used; native behavior validated directly which is stronger for this purpose).

### Tertiary (LOW confidence)
- `os.lf_saw` availability (A3) and FM-mod-depth target feasibility (A2) — training-knowledge assumptions, not validated; both out of v1.1 scope.

## Metadata

**Confidence breakdown:**
- Faust LFO idioms + determinism: HIGH — validated empirically against the exact engine/version this session.
- Backward-compat / bit-identity: HIGH — depth-0 `array_equal` confirmed; recommended "emit v1.0 string when absent" is strictly safer.
- Manifest schema + validation: HIGH — direct extension of the existing `_check_number` discipline.
- Mel time-variation test: HIGH — measured through the frozen extractor.
- Musical-parameter defaults (cents, multi-carrier choice): MEDIUM — flagged as discuss-phase decisions (A1, A4).

**Research date:** 2026-06-02
**Valid until:** 2026-09-02 (stable — pinned dawdreamer 0.8.3, frozen mel contract; re-validate determinism if dawdreamer/Faust wheel is bumped)

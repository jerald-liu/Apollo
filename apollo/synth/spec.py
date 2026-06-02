"""Frozen FM spec — the single source of truth Phase 5's browser synth mirrors.

Owns four things: the FM parameter schema (ranges/defaults), the algorithm set
(fixed 3-op routing topologies), envelope semantics (per-operator ADSR), and the
determinism-critical engine constants. `dsp_string()` is the ONLY place a Faust
patch is constructed.

Do not mutate field ranges, algorithm semantics, the engine constants, or the
Faust templates without bumping `SPEC_VERSION` — any change can re-render an
already-authored corpus differently (breaks determinism reproducibility, and
shifts the mel distribution the encoder was trained on). New operators /
algorithms bump the version and are handled explicitly (the v1 engine is
fixed at 3 operators / 3 algorithms; the full 4-op/11-algorithm topology is
deferred to SEED-009).

Layout (see .planning/phases/06-synth-independent-corpus-rendering/06-RESEARCH.md
§"FM Spec Module", §"3-Op Faust Patch"):

    Algorithm   3 fixed routings (STACK / PARALLEL_MODS / CARRIER_PAIR)
    OperatorParams  per-op: ratio, level, attack, decay, sustain, release
    FmParams        algorithm + exactly-3 operators + master gain
    Engine consts   SR / BLOCK / NUM_VOICES / TARGET_PEAK (spike 001)

SECURITY (RESEARCH §"Security Domain" — Faust DSP injection): `dsp_string`
substitutes NUMERIC params only. No string field from a manifest is ever
interpolated into the DSP source. The manifest carries numbers/ints only.

v1.1 (Phase 7) adds ONE optional global LFO (`FmParams.lfo`) — rate/depth/wave/
target — modulating either carrier LEVEL (tremolo) or carrier PITCH (vibrato).
The loader accepts both `"1.0"` and `"1.1"` manifests; a v1.0 / no-`lfo` patch
renders BIT-IDENTICALLY to Phase 6 because `dsp_string` emits the exact v1.0
source string when `lfo is None` (RESEARCH Pitfall 1 — strictly safer than
depth-0 wiring). The LFO block obeys the same numeric-only rule: waveform is
selected by `select3(int(lfo_wave), ...)`, target by a Python branch choosing
which NUMERIC wiring to emit — no enum name is ever interpolated.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

# Spec version string. Written into every per-pair manifest (`call_fm.json`) and
# checked by manifest.load_manifest — an old corpus cannot silently re-render
# under a changed spec. Mirror vocab.py's "do not mutate without bumping" rule.
SPEC_VERSION = "1.1"


class Algorithm(IntEnum):
    """Fixed 3-operator routing topologies (v1 — exactly 3, not 4-op/11-alg).

    Operators are numbered 1..3 in the classic FM sense; in code/manifest they
    are the 0-based `operators` tuple, where index i corresponds to op (i+1).
    A "modulator" feeds another operator's frequency; a "carrier" is summed
    into the audio output.
    """

    STACK = 0          # 3 -> 2 -> 1 chained modulation (one carrier: op1)
    PARALLEL_MODS = 1  # (2 + 3) -> 1 two modulators summed into one carrier (op1)
    CARRIER_PAIR = 2   # 3 -> 1 plus op2 as an independent additive carrier


class LfoWave(IntEnum):
    """LFO waveform (v1.1). Selected at render time by a NUMERIC `lfo_wave`
    hslider routed through Faust `select3(int(lfo_wave), ...)` — the enum name is
    never interpolated into the DSP source.
    """

    SINE = 0
    TRIANGLE = 1
    SQUARE = 2
    # reserve 3 = SAW for a later spec bump — do NOT implement in v1.1


class LfoTarget(IntEnum):
    """What the LFO modulates (v1.1). Selected by a Python branch in `dsp_string`
    that chooses which NUMERIC wiring to emit (like `algorithm`).
    """

    LEVEL = 0   # tremolo (scales carrier output)
    PITCH = 1   # vibrato (scales carrier frequency in cents)
    # reserve 2 = FM-mod-depth for a later spec bump — do NOT implement in v1.1


@dataclass(frozen=True)
class LfoParams:
    """One optional global LFO for an FM patch (v1.1).

    Frozen so `FmParams` stays hashable. `wave`/`target` are LfoWave/LfoTarget
    integer values; the loader validates them as ints (never strings).

    Fields:
        rate    LFO frequency in Hz, [0.05, 20.0]
        depth   modulation depth [0.0, 1.0] (0 ⇒ no audible modulation)
        wave    LfoWave value {0:sine, 1:triangle, 2:square}
        target  LfoTarget value {0:level (tremolo), 1:pitch (vibrato)}
    """

    rate: float
    depth: float
    wave: int
    target: int


@dataclass(frozen=True)
class OperatorParams:
    """One FM operator: oscillator ratio, output/mod level, and its own ADSR.

    Per-op ADSR is what makes the FM family expressive (RESEARCH §"3-Op Faust
    Patch"). Frozen so FmParams stays hashable and the spec is immutable.

    Fields:
        ratio    frequency multiplier of the note fundamental (Faust `op{i}_ratio`)
        level    operator output / modulation depth in [0, 1] (`op{i}_level`)
        attack   ADSR attack seconds  (`op{i}_attack`)
        decay    ADSR decay seconds   (`op{i}_decay`)
        sustain  ADSR sustain level [0, 1] (`op{i}_sustain`)
        release  ADSR release seconds (`op{i}_release`)
    """

    ratio: float
    level: float
    attack: float
    decay: float
    sustain: float
    release: float


@dataclass(frozen=True)
class FmParams:
    """Full FM patch for one pair: routing + exactly 3 operators + master gain.

    `operators` is a tuple (not a list) so the dataclass stays frozen/hashable.
    Exactly 3 entries — enforced upstream by manifest.load_manifest.

    `lfo` is the optional v1.1 global LFO. It is the TRAILING field so existing
    positional/keyword v1.0 constructor calls are unchanged; `None` ⇒ the patch
    renders bit-identically to Phase 6.
    """

    algorithm: int
    operators: tuple[OperatorParams, ...]
    gain: float
    lfo: LfoParams | None = None


# ---- Engine config (determinism-critical; spike 001) ----
# These are baked into every render. Changing any of them re-renders the corpus
# differently, so they live in the versioned spec, not in render.py.
SR = 44100          # render sample rate (MelExtractor resamples to 22050 itself)
BLOCK = 512         # DawDreamer block size
NUM_VOICES = 8      # polyphony so overlapping note releases are not cut (spike 001)
TARGET_PEAK = 0.89  # ~ -1 dBFS headroom before PCM write (A2; spike saw peaks > 1.0)


def dsp_string(p: FmParams) -> str:
    """Build a deterministic Faust DSP source for `p` from numeric params only.

    Selects one of three templates by `p.algorithm`. Each operator gets its own
    `en.adsr(...)` envelope plus `op{i}_ratio` / `op{i}_level` hsliders. `freq`,
    `gain`, and `gate` are MIDI-owned (consumed by DawDreamer's MIDI layer) and
    are NOT settable params. Output is a single mono `_` (mono halves file size
    and removes L/R asymmetry as a determinism variable — RESEARCH).

    SECURITY (RESEARCH §"Security Domain"): only numeric values from `p` are
    formatted into the source. No string field is ever interpolated.

    The per-op slider NAMES this emits are `op{i}_ratio`, `op{i}_level`,
    `op{i}_attack`, `op{i}_decay`, `op{i}_sustain`, `op{i}_release` for i in
    1..3 (1-based to match classic FM operator numbering). render.py (Plan
    06-02) resolves these names -> integer indices at runtime via
    `get_parameters_description()` (do NOT hardcode a static index map — spike
    landmine).
    """
    algorithm = int(p.algorithm)
    if algorithm not in (a.value for a in Algorithm):
        raise ValueError(f"unknown algorithm {algorithm!r}; expected one of {[a.value for a in Algorithm]}")
    if len(p.operators) != 3:
        raise ValueError(f"dsp_string requires exactly 3 operators, got {len(p.operators)}")

    # Per-operator slider + envelope declarations. `i` is 1-based for slider
    # names (op1..op3); `op` is the 0-based OperatorParams. All substituted
    # values are floats — never strings.
    decls: list[str] = ['import("stdfaust.lib");',
                         'freq = hslider("freq", 440, 20, 20000, 0.01);   // MIDI-owned',
                         'gain = hslider("gain", 0.5, 0, 1, 0.01);        // MIDI-owned',
                         'gate = button("gate");                           // MIDI-owned']
    for i, op in enumerate(p.operators, start=1):
        decls.append(
            f'op{i}_ratio = hslider("op{i}_ratio", {float(op.ratio):.6f}, 0.5, 12, 0.01);'
        )
        decls.append(
            f'op{i}_level = hslider("op{i}_level", {float(op.level):.6f}, 0, 1, 0.01);'
        )
        decls.append(
            f'op{i}_env = en.adsr('
            f'{float(op.attack):.6f}, {float(op.decay):.6f}, '
            f'{float(op.sustain):.6f}, {float(op.release):.6f}, gate);'
        )
        # An operator's oscillator at its ratio, scaled by its own envelope.
        decls.append(f'op{i} = os.osc(freq * op{i}_ratio) * op{i}_env;')

    header = "\n".join(decls)

    if p.lfo is None:
        # No LFO ⇒ emit the EXACT Phase-6 v1.0 source (RESEARCH Pitfall 1:
        # bit-identity is preserved by emitting the SAME source string, not by
        # wiring a depth-0 LFO). Do NOT add any lfo_* declarations here.
        body = _body_no_lfo(algorithm)
        return f"{header}\n{body}\n"

    # ---- v1.1 LFO block (numeric-only) -------------------------------------
    # Waveform is selected by select3(int(lfo_wave), ...); rate/depth are :.6f
    # floats; wave is an int. NO enum NAME is interpolated (T-07-01). `target`
    # selects WHICH numeric wiring is emitted via a Python branch below.
    lfo = p.lfo
    lfo_decls = [
        f'lfo_rate = hslider("lfo_rate", {float(lfo.rate):.6f}, 0.05, 20, 0.001);',
        f'lfo_depth = hslider("lfo_depth", {float(lfo.depth):.6f}, 0, 1, 0.001);',
        f'lfo_wave = hslider("lfo_wave", {int(lfo.wave)}, 0, 2, 1);',
        "lfo_bi = select3(int(lfo_wave), os.osc(lfo_rate), "
        "os.lf_triangle(lfo_rate), os.lf_squarewave(lfo_rate));",
    ]
    header = header + "\n" + "\n".join(lfo_decls)

    target = int(lfo.target)
    if target == LfoTarget.LEVEL:
        # Tremolo: unipolar gain in [1-depth, 1], multiplied into each CARRIER.
        # ORCHESTRATOR DEFAULT A4: applied to ALL carriers uniformly (one global
        # LFO ⇒ both CARRIER_PAIR carriers move together).
        header = header + (
            "\nlfo_uni = (lfo_bi + 1.0) / 2.0;"
            "\nlvl_mod = 1.0 - lfo_depth * (1.0 - lfo_uni);"
        )
        body = _body_lfo_level(algorithm)
    else:  # LfoTarget.PITCH
        # Vibrato: scale each carrier oscillator's freq argument by pitch_mul.
        # ORCHESTRATOR DEFAULT A1: 50-cent max deviation at depth=1 (musical
        # vibrato; discuss-phase could refine to 100 for dramatic). 50.0 is a
        # baked Faust numeric literal. Applied to ALL carriers (A4).
        header = header + (
            "\npitch_mul = pow(2.0, (lfo_bi * lfo_depth * 50.0) / 1200.0);"
        )
        body = _body_lfo_pitch(algorithm)

    return f"{header}\n{body}\n"


def _body_no_lfo(algorithm: int) -> str:
    """The verbatim Phase-6 v1.0 routing body (no modulation applied)."""
    if algorithm == Algorithm.STACK:
        # 3 -> 2 -> 1 chain; op1 is the sole carrier.
        return (
            "mod3 = op3 * op3_level * freq;\n"
            "mod2 = os.osc(freq * op2_ratio + mod3) * op2_env * op2_level * freq;\n"
            "car  = os.osc(freq * op1_ratio + mod2) * op1_env * op1_level;\n"
            "process = car * gain;"
        )
    if algorithm == Algorithm.PARALLEL_MODS:
        # (2 + 3) -> 1; two modulators summed into one carrier (op1).
        return (
            "mod2 = op2 * op2_level * freq;\n"
            "mod3 = op3 * op3_level * freq;\n"
            "car  = os.osc(freq * op1_ratio + mod2 + mod3) * op1_env * op1_level;\n"
            "process = car * gain;"
        )
    # Algorithm.CARRIER_PAIR: 3 -> 1 modulation, plus op2 as additive carrier.
    return (
        "mod3 = op3 * op3_level * freq;\n"
        "car1 = os.osc(freq * op1_ratio + mod3) * op1_env * op1_level;\n"
        "car2 = op2 * op2_level;\n"
        "process = (car1 + car2) * gain;"
    )


def _body_lfo_level(algorithm: int) -> str:
    """v1.0 routing with `* lvl_mod` multiplied into each carrier (tremolo)."""
    if algorithm == Algorithm.STACK:
        return (
            "mod3 = op3 * op3_level * freq;\n"
            "mod2 = os.osc(freq * op2_ratio + mod3) * op2_env * op2_level * freq;\n"
            "car  = os.osc(freq * op1_ratio + mod2) * op1_env * op1_level * lvl_mod;\n"
            "process = car * gain;"
        )
    if algorithm == Algorithm.PARALLEL_MODS:
        return (
            "mod2 = op2 * op2_level * freq;\n"
            "mod3 = op3 * op3_level * freq;\n"
            "car  = os.osc(freq * op1_ratio + mod2 + mod3) * op1_env * op1_level * lvl_mod;\n"
            "process = car * gain;"
        )
    # CARRIER_PAIR: lvl_mod on BOTH carriers (orchestrator default A4).
    return (
        "mod3 = op3 * op3_level * freq;\n"
        "car1 = os.osc(freq * op1_ratio + mod3) * op1_env * op1_level * lvl_mod;\n"
        "car2 = op2 * op2_level * lvl_mod;\n"
        "process = (car1 + car2) * gain;"
    )


def _body_lfo_pitch(algorithm: int) -> str:
    """v1.0 routing with each carrier osc freq arg scaled by `pitch_mul` (vibrato)."""
    if algorithm == Algorithm.STACK:
        return (
            "mod3 = op3 * op3_level * freq;\n"
            "mod2 = os.osc(freq * op2_ratio + mod3) * op2_env * op2_level * freq;\n"
            "car  = os.osc(freq * op1_ratio * pitch_mul + mod2) * op1_env * op1_level;\n"
            "process = car * gain;"
        )
    if algorithm == Algorithm.PARALLEL_MODS:
        return (
            "mod2 = op2 * op2_level * freq;\n"
            "mod3 = op3 * op3_level * freq;\n"
            "car  = os.osc(freq * op1_ratio * pitch_mul + mod2 + mod3) * op1_env * op1_level;\n"
            "process = car * gain;"
        )
    # CARRIER_PAIR: vibrato on BOTH carriers (orchestrator default A4). car2 is
    # op2's oscillator (`os.osc(freq * op2_ratio)` baked in op2), so we re-emit
    # it here scaled by pitch_mul instead of reusing the un-vibrato'd `op2`.
    return (
        "mod3 = op3 * op3_level * freq;\n"
        "car1 = os.osc(freq * op1_ratio * pitch_mul + mod3) * op1_env * op1_level;\n"
        "car2 = os.osc(freq * op2_ratio * pitch_mul) * op2_env * op2_level;\n"
        "process = (car1 + car2) * gain;"
    )

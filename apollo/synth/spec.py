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
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

# Spec version string. Written into every per-pair manifest (`call_fm.json`) and
# checked by manifest.load_manifest — an old corpus cannot silently re-render
# under a changed spec. Mirror vocab.py's "do not mutate without bumping" rule.
SPEC_VERSION = "1.0"


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
    """

    algorithm: int
    operators: tuple[OperatorParams, ...]
    gain: float


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

    # Modulation depth convention: a modulator deviates the carrier frequency by
    # (modulator_output * level * freq). Carriers are scaled by their level and
    # the master `gain`. Templates differ only in routing.
    if algorithm == Algorithm.STACK:
        # 3 -> 2 -> 1 chain; op1 is the sole carrier.
        body = (
            "mod3 = op3 * op3_level * freq;\n"
            "mod2 = os.osc(freq * op2_ratio + mod3) * op2_env * op2_level * freq;\n"
            "car  = os.osc(freq * op1_ratio + mod2) * op1_env * op1_level;\n"
            "process = car * gain;"
        )
    elif algorithm == Algorithm.PARALLEL_MODS:
        # (2 + 3) -> 1; two modulators summed into one carrier (op1).
        body = (
            "mod2 = op2 * op2_level * freq;\n"
            "mod3 = op3 * op3_level * freq;\n"
            "car  = os.osc(freq * op1_ratio + mod2 + mod3) * op1_env * op1_level;\n"
            "process = car * gain;"
        )
    else:  # Algorithm.CARRIER_PAIR
        # 3 -> 1 modulation, plus op2 as an independent additive carrier.
        body = (
            "mod3 = op3 * op3_level * freq;\n"
            "car1 = os.osc(freq * op1_ratio + mod3) * op1_env * op1_level;\n"
            "car2 = op2 * op2_level;\n"
            "process = (car1 + car2) * gain;"
        )

    return f"{header}\n{body}\n"

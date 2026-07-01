"""Per-pair FM manifest loader + validator (the untrusted-input boundary).

Loads a hand-authored `call_fm.json` and returns a validated `FmParams`, or
raises `IngestError(pair_path, reason)` naming the offending pair/field. This is
the fail-loud trust boundary between author-on-disk and the renderer's parameter
space (see threat register T-06-01..T-06-04). Mirrors the parse -> validate ->
raise-IngestError discipline of `apollo/ingest/midi.py::load_notes`.

Manifest schema (spec_version "1.0" or "1.1"):

    {
      "spec_version": "1.1",                // "1.0" OR "1.1"; lfo REQUIRES "1.1"
      "algorithm": 0,                       // int in 0..len(Algorithm)-1
      "operators": [                        // EXACTLY 3
        {"ratio": .., "level": .., "attack": ..,
         "decay": .., "sustain": .., "release": ..},
        ... (3 total)
      ],
      "gain": 0.5,
      "lfo": {                              // OPTIONAL (v1.1 only); omit => Phase-6 identical
        "rate": 6.0,                        // Hz, [0.05, 20.0]
        "depth": 0.8,                       // [0.0, 1.0]
        "wave": 0,                          // int {0:sine, 1:triangle, 2:square}
        "target": 0                         // int {0:level (tremolo), 1:pitch (vibrato)}
      }
    }

SECURITY (RESEARCH §"Security Domain"): every numeric field is type-checked,
NaN/Inf-rejected (`math.isfinite`), and range-checked; enum fields (wave/target)
are validated ints. Manifest values are numbers/ints only — no string is ever
accepted into a field that could reach the Faust DSP source (T-06-01, T-06-03).
Only `spec_version ∈ {"1.0","1.1"}` is accepted, and an `lfo` block under
`"1.0"` is rejected (version downgrade carrying lfo), so an old corpus cannot
silently re-render under a changed spec (T-06-02, T-07-03).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from apollo.ingest.errors import IngestError
from apollo.synth.spec import (
    SPEC_VERSION,
    Algorithm,
    FmParams,
    LfoParams,
    LfoTarget,
    LfoWave,
    OperatorParams,
)

# Accepted manifest spec versions. v1.0 (no lfo) and v1.1 (optional lfo) both
# load; SPEC_VERSION is the version this code WRITES. A v1.0 manifest renders
# bit-identically (spec.dsp_string emits the verbatim v1.0 source when no lfo).
SUPPORTED_VERSIONS = {"1.0", "1.1"}

# ---- Validation bounds (decision-citing; mirror midi.py module constants) ----
# Exactly 3 operators in v1 (RESEARCH §"3-Op Faust Patch"). Rejecting != 3
# bounds the param surface (T-06-04) and matches the fixed Algorithm topologies.
N_OPERATORS = 3

# Field ranges (RESEARCH §"Manifest Schema" field-ranges table). These mirror
# the Faust hslider ranges declared in spec.dsp_string so a manifest can never
# request a value the DSP would silently clamp.
RATIO_MIN, RATIO_MAX = 0.5, 12.0     # frequency multiplier
LEVEL_MIN, LEVEL_MAX = 0.0, 1.0      # operator output / modulation depth
GAIN_MIN, GAIN_MAX = 0.0, 1.0        # master gain
ADSR_MIN, ADSR_MAX = 0.0, 2.0        # attack / decay / release seconds
SUSTAIN_MIN, SUSTAIN_MAX = 0.0, 1.0  # ADSR sustain level

# LFO bounds (v1.1; RESEARCH §"Manifest Schema"). Rate capped at 20 Hz (the LFO
# never extends render length, so the existing duration cap remains the DoS
# bound — T-07-04); depth in [0,1]. Mirror the spec.dsp_string hslider ranges.
LFO_RATE_MIN, LFO_RATE_MAX = 0.05, 20.0
LFO_DEPTH_MIN, LFO_DEPTH_MAX = 0.0, 1.0

# Per-operator numeric fields and their bounds. Order is the OperatorParams
# constructor order.
_OP_FIELDS = (
    ("ratio", RATIO_MIN, RATIO_MAX),
    ("level", LEVEL_MIN, LEVEL_MAX),
    ("attack", ADSR_MIN, ADSR_MAX),
    ("decay", ADSR_MIN, ADSR_MAX),
    ("sustain", SUSTAIN_MIN, SUSTAIN_MAX),
    ("release", ADSR_MIN, ADSR_MAX),
)


def _check_number(value: object, pair_path: str, label: str, lo: float, hi: float) -> float:
    """Return `value` as a finite float in [lo, hi], else raise IngestError.

    Rejects bools (a stray `true`/`false` is not a valid numeric param) and
    NaN/Inf (T-06-01 Tampering mitigation).
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise IngestError(pair_path, f"{label} must be a number, got {type(value).__name__}")
    num = float(value)
    if not math.isfinite(num):
        raise IngestError(pair_path, f"{label} must be finite, got {value!r}")
    if not (lo <= num <= hi):
        raise IngestError(pair_path, f"{label} {num} out of range [{lo}, {hi}]")
    return num


def _check_enum_int(value: object, pair_path: str, label: str, valid: set[int]) -> int:
    """Return `value` as an int in `valid`, else raise IngestError.

    Mirrors the algorithm guard: rejects bools (a stray `true`/`false` is not a
    valid enum int) and non-int values, then membership-checks (T-07-02).
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise IngestError(pair_path, f"{label} must be an int, got {type(value).__name__}")
    if value not in valid:
        raise IngestError(pair_path, f"{label} {value} not in {sorted(valid)}")
    return value


def load_manifest(path: str, pair_path: str) -> FmParams:
    """Load and validate a `call_fm.json`, returning a frozen `FmParams`.

    Raises `IngestError(pair_path, reason)` on: parse failure, unsupported
    `spec_version`, missing/invalid `algorithm`, operator count != 3, or any
    per-field type/finite/range violation.
    """
    try:
        raw = json.loads(Path(path).read_text())
    except Exception as e:
        raise IngestError(pair_path, f"failed to parse {path}: {e}")

    if not isinstance(raw, dict):
        raise IngestError(pair_path, f"{path} must be a JSON object, got {type(raw).__name__}")

    # Version guard (T-06-02): accept only known versions. v1.0 and v1.1 both
    # load (a v1.0 manifest renders bit-identically). `version` stays bound for
    # the lfo-requires-1.1 cross-check below.
    version = raw.get("spec_version")
    if version not in SUPPORTED_VERSIONS:
        raise IngestError(
            pair_path,
            f"manifest spec_version {version!r} not in {sorted(SUPPORTED_VERSIONS)}",
        )

    # Algorithm guard: must be an int identifying one of the fixed topologies.
    algorithm = raw.get("algorithm")
    if isinstance(algorithm, bool) or not isinstance(algorithm, int):
        raise IngestError(pair_path, f"algorithm must be an int, got {algorithm!r}")
    if algorithm not in (a.value for a in Algorithm):
        valid = [a.value for a in Algorithm]
        raise IngestError(pair_path, f"algorithm {algorithm} not in {valid}")

    # Operator-count guard (T-06-04).
    ops = raw.get("operators")
    if not isinstance(ops, list):
        raise IngestError(pair_path, f"operators must be a list, got {type(ops).__name__}")
    if len(ops) != N_OPERATORS:
        raise IngestError(
            pair_path, f"expected exactly {N_OPERATORS} operators, got {len(ops)}"
        )

    operators: list[OperatorParams] = []
    for idx, op in enumerate(ops):
        if not isinstance(op, dict):
            raise IngestError(pair_path, f"operator {idx} must be an object, got {type(op).__name__}")
        values: dict[str, float] = {}
        for field, lo, hi in _OP_FIELDS:
            if field not in op:
                raise IngestError(pair_path, f"operator {idx} missing field {field!r}")
            values[field] = _check_number(op[field], pair_path, f"operator {idx} {field}", lo, hi)
        operators.append(OperatorParams(**values))

    if "gain" not in raw:
        raise IngestError(pair_path, "missing field 'gain'")
    gain = _check_number(raw["gain"], pair_path, "gain", GAIN_MIN, GAIN_MAX)

    # Optional LFO block (v1.1). Absent => lfo=None => Phase-6 identical render.
    # SECURITY (T-07-02/03): numbers/ints only; reject lfo under "1.0", reject a
    # non-object lfo, and fail-loud on every field (range/finite/enum/bool).
    lfo = None
    raw_lfo = raw.get("lfo")
    if raw_lfo is not None:
        if version != "1.1":
            raise IngestError(pair_path, "lfo block requires spec_version '1.1'")
        if not isinstance(raw_lfo, dict):
            raise IngestError(pair_path, f"lfo must be an object, got {type(raw_lfo).__name__}")
        rate = _check_number(raw_lfo.get("rate"), pair_path, "lfo rate", LFO_RATE_MIN, LFO_RATE_MAX)
        depth = _check_number(raw_lfo.get("depth"), pair_path, "lfo depth", LFO_DEPTH_MIN, LFO_DEPTH_MAX)
        wave = _check_enum_int(raw_lfo.get("wave"), pair_path, "lfo wave", {w.value for w in LfoWave})
        target = _check_enum_int(raw_lfo.get("target"), pair_path, "lfo target", {t.value for t in LfoTarget})
        lfo = LfoParams(rate=rate, depth=depth, wave=wave, target=target)

    return FmParams(algorithm=algorithm, operators=tuple(operators), gain=gain, lfo=lfo)

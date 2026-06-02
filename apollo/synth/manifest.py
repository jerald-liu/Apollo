"""Per-pair FM manifest loader + validator (the untrusted-input boundary).

Loads a hand-authored `call_fm.json` and returns a validated `FmParams`, or
raises `IngestError(pair_path, reason)` naming the offending pair/field. This is
the fail-loud trust boundary between author-on-disk and the renderer's parameter
space (see threat register T-06-01..T-06-04). Mirrors the parse -> validate ->
raise-IngestError discipline of `apollo/ingest/midi.py::load_notes`.

Manifest schema (spec_version "1.0"):

    {
      "spec_version": "1.0",
      "algorithm": 0,                       // int in 0..len(Algorithm)-1
      "operators": [                        // EXACTLY 3
        {"ratio": .., "level": .., "attack": ..,
         "decay": .., "sustain": .., "release": ..},
        ... (3 total)
      ],
      "gain": 0.5
    }

SECURITY (RESEARCH §"Security Domain"): every numeric field is type-checked,
NaN/Inf-rejected (`math.isfinite`), and range-checked. Manifest values are
numbers/ints only — no string is ever accepted into a field that could reach
the Faust DSP source (T-06-01, T-06-03). Unknown `spec_version` is rejected so
an old corpus cannot silently re-render under a changed spec (T-06-02).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from apollo.ingest.errors import IngestError
from apollo.synth.spec import SPEC_VERSION, Algorithm, FmParams, OperatorParams

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

    # Version guard (T-06-02): reject unknown versions outright.
    version = raw.get("spec_version")
    if version != SPEC_VERSION:
        raise IngestError(
            pair_path,
            f"manifest spec_version {version!r} != supported {SPEC_VERSION!r}",
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

    return FmParams(algorithm=algorithm, operators=tuple(operators), gain=gain)

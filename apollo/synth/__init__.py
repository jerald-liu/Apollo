"""Apollo synth package — headless FM renderer (DawDreamer + Faust).

Public surface:
    - SPEC_VERSION     (str constant; written into every manifest)
    - Algorithm        (IntEnum: fixed 3-op operator-routing topologies)
    - LfoWave          (IntEnum: LFO waveform {sine, triangle, square})
    - LfoTarget        (IntEnum: LFO target {level (tremolo), pitch (vibrato)})
    - LfoParams        (frozen dataclass: optional v1.1 global LFO)
    - FmParams         (frozen dataclass: full 3-op FM parameter set + optional lfo)
    - OperatorParams   (frozen dataclass: one operator's ratio/level/ADSR)
    - dsp_string       (FmParams -> Faust DSP source; only place a patch is built)
    - load_manifest    (path, pair_path -> FmParams; IngestError on bad input)
    - render           (params, notes -> np.ndarray; deterministic + normalized)
    - render_call_wav  (manifest_path, mid_path -> np.ndarray; shared parity path)
"""

from .manifest import load_manifest
from .render import render, render_call_wav
from .spec import (
    SPEC_VERSION,
    Algorithm,
    FmParams,
    LfoParams,
    LfoTarget,
    LfoWave,
    OperatorParams,
    dsp_string,
)

__all__ = [
    "SPEC_VERSION",
    "Algorithm",
    "LfoWave",
    "LfoTarget",
    "LfoParams",
    "FmParams",
    "OperatorParams",
    "dsp_string",
    "load_manifest",
    "render",
    "render_call_wav",
]

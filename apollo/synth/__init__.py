"""Apollo synth package — headless FM renderer (DawDreamer + Faust).

Public surface:
    - SPEC_VERSION     (str constant; written into every manifest)
    - Algorithm        (IntEnum: fixed 3-op operator-routing topologies)
    - FmParams         (frozen dataclass: full 3-op FM parameter set)
    - OperatorParams   (frozen dataclass: one operator's ratio/level/ADSR)
    - dsp_string       (FmParams -> Faust DSP source; only place a patch is built)
    - load_manifest    (path, pair_path -> FmParams; IngestError on bad input)

Note: `render` / `render_call_wav` (the DawDreamer render path) are added in
Plan 06-02 — this package init does NOT import a `.render` module yet.
"""

from .manifest import load_manifest
from .spec import SPEC_VERSION, Algorithm, FmParams, OperatorParams, dsp_string

__all__ = [
    "SPEC_VERSION",
    "Algorithm",
    "FmParams",
    "OperatorParams",
    "dsp_string",
    "load_manifest",
]

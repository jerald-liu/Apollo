"""Apollo tokenizer package — vocab constants + quantization helpers.

Public surface (the only names downstream code should import):

    from apollo.tokenizer import (
        Vocab,
        DURATION_EDGES,
        quantize_duration, decode_duration,
        quantize_time_shift, decode_time_shift,
        quantize_velocity, decode_velocity,
    )
"""

from .bins import (
    DURATION_EDGES,
    decode_duration,
    decode_time_shift,
    decode_velocity,
    quantize_duration,
    quantize_time_shift,
    quantize_velocity,
)
from .encoder import Tokenizer
from .types import Note
from .vocab import Vocab

__all__ = [
    "Vocab",
    "DURATION_EDGES",
    "quantize_duration",
    "decode_duration",
    "quantize_time_shift",
    "decode_time_shift",
    "quantize_velocity",
    "decode_velocity",
    "Note",
    "Tokenizer",
]

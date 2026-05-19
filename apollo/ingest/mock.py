"""Mock pair synthesis for tests. NOT part of production pipeline.

`synthesize_pair(out_dir, nnn)` writes `<out_dir>/<nnn>/{call.mid, call.wav,
response.mid}` with content satisfying every ingest invariant:

  - call.mid and response.mid have exactly one Instrument track, monophonic
    non-overlapping notes, tempo=120 bpm, and at least one note in [C2..C5].
  - call.wav is a 1-second 440 Hz sine tone at `audio_sr` (default 44100 Hz);
    content is irrelevant to the model — only shape/format matter for the
    MelExtractor.

The function takes an explicit `out_dir`; callers control the path. The
docstring + module name flag this as a test helper (T-01-17 disposition:
accept — production CLI does not import this module).

See .planning/phases/01-tokenizer-ingest/01-RESEARCH.md §"Mock Pair Generation".
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pretty_midi
import torch
import torchaudio


def synthesize_pair(
    out_dir: Path,
    nnn: str = "000",
    call_pitches=(60, 62, 64),
    call_durs=(0.5, 0.5, 0.5),
    response_pitches=(67, 65, 64),
    response_durs=(0.5, 0.5, 0.5),
    audio_sr: int = 44100,
    audio_seconds: float = 1.5,
) -> Path:
    """Write `<out_dir>/<nnn>/{call.mid, call.wav, response.mid}` for tests.

    Returns the pair directory path. Notes are placed back-to-back starting
    at t=0 with no overlap; tempo is fixed at 120 bpm via
    `pretty_midi.PrettyMIDI(initial_tempo=120.0)`.

    Default durations are 0.5 s (quarter note at 120 bpm) so that
    `pretty_midi.estimate_tempo()` returns 120.0 — required for
    `load_notes` to pass the ±2 bpm tempo guard. The RESEARCH.md snippet
    used 0.25 s, which trips estimate_tempo into reporting 240 bpm; that
    was caught by `test_ingest_ten_pairs_end_to_end` in plan 01-05.
    `audio_seconds` is 1.5 s by default to cover three quarter notes.
    """
    pair_dir = Path(out_dir) / nnn
    pair_dir.mkdir(parents=True, exist_ok=True)

    def write_midi(path: Path, pitches, durations, velocity=80):
        pm = pretty_midi.PrettyMIDI(initial_tempo=120.0)
        inst = pretty_midi.Instrument(program=0)
        t = 0.0
        for p, d in zip(pitches, durations):
            inst.notes.append(
                pretty_midi.Note(velocity=velocity, pitch=p, start=t, end=t + d)
            )
            t += d
        pm.instruments.append(inst)
        pm.write(str(path))

    write_midi(pair_dir / "call.mid", call_pitches, call_durs)
    write_midi(pair_dir / "response.mid", response_pitches, response_durs)

    # 440 Hz sine — content doesn't matter, just shape/format for MelExtractor.
    t = np.arange(int(audio_seconds * audio_sr)) / audio_sr
    wav = (0.1 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    wav_tensor = torch.from_numpy(wav).unsqueeze(0)  # (1, samples)
    torchaudio.save(str(pair_dir / "call.wav"), wav_tensor, audio_sr)

    return pair_dir

"""Apollo audio synthesis pipeline.

Converts generated MIDI to WAV using one of three backends (in order of quality):
  1. FluidSynth + soundfont  (best — requires `brew install fluidsynth` + pyfluidsynth)
  2. EnCodec encoder-decoder  (neural polish on top of any audio)
  3. Additive sine synthesis  (no external deps — fallback)

Usage:
    # Basic synthesis:
    python scripts/synthesize.py --midi data/processed/generated/step49999_t07.mid

    # All generated MIDIs in a directory:
    python scripts/synthesize.py --midi data/processed/generated/ --all

    # With EnCodec neural polish:
    python scripts/synthesize.py --midi step49999_t07.mid --encodec

    # From generate.py (called automatically with --audio flag):
    synthesize_midi(midi_path, wav_path, use_encodec=False)
"""

import argparse
import sys
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Soundfont management
# ---------------------------------------------------------------------------

SOUNDFONT_DIR  = Path.home() / ".apollo"
SOUNDFONT_PATH = SOUNDFONT_DIR / "GeneralUser_GS.sf2"

# Reliable CC0 GM soundfont (~30MB) — MuseScore's bundled font
_SF2_DOWNLOAD_URL = (
    "https://ftp.osuosl.org/pub/musescore/soundfont/MuseScore_General.sf3"
)

# SF2 bundled with FluidSynth (brew install fluidsynth) — good fallback
_BREW_SF2 = Path("/opt/homebrew/Cellar").glob("fluid-synth/*/share/fluid-synth/sf2/VintageDreamsWaves-v2.sf2")

_sf2_cache = None  # module-level cache so we only search once


def ensure_soundfont():
    """Return path to a usable SF2, downloading if needed. Caches result."""
    global _sf2_cache
    if _sf2_cache is not None:
        return _sf2_cache

    # 1. Already downloaded
    if SOUNDFONT_PATH.exists():
        _sf2_cache = SOUNDFONT_PATH
        return _sf2_cache

    # 2. Bundled with brew fluidsynth
    for p in sorted(Path("/opt/homebrew/Cellar").glob(
        "fluid-synth/*/share/fluid-synth/sf2/VintageDreamsWaves-v2.sf2"
    )):
        if p.exists():
            print(f"  Using bundled soundfont: {p.name}")
            _sf2_cache = p
            return _sf2_cache

    # 3. Try to download GeneralUser GS
    try:
        import urllib.request
        SOUNDFONT_DIR.mkdir(parents=True, exist_ok=True)
        print(f"Downloading soundfont to {SOUNDFONT_PATH} (~30MB)...")
        urllib.request.urlretrieve(_SF2_DOWNLOAD_URL, SOUNDFONT_PATH)
        _sf2_cache = SOUNDFONT_PATH
        return _sf2_cache
    except Exception as e:
        print(f"  Soundfont download failed: {e} — using additive synthesis")
        _sf2_cache = False  # sentinel: don't retry
        return None


# ---------------------------------------------------------------------------
# Backend 1: FluidSynth via pretty_midi
# ---------------------------------------------------------------------------

def _synthesize_fluidsynth(midi_path: str, sample_rate: int = 44100):
    """Render via fluidsynth CLI. Returns float32 array or None if unavailable."""
    import shutil, subprocess, tempfile, soundfile as sf_lib
    fluidsynth_bin = shutil.which("fluidsynth") or "/opt/homebrew/bin/fluidsynth"
    if not Path(fluidsynth_bin).exists():
        return None
    soundfont = ensure_soundfont()
    if soundfont is None:
        return None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
        result = subprocess.run(
            [fluidsynth_bin, "-ni", "-F", tmp_path, "-r", str(sample_rate),
             str(soundfont), str(midi_path)],
            capture_output=True, timeout=120,
        )
        if result.returncode != 0 or not Path(tmp_path).exists():
            return None
        audio, _ = sf_lib.read(tmp_path, dtype="float32")
        Path(tmp_path).unlink(missing_ok=True)
        # Mix to mono if stereo
        if audio.ndim == 2:
            audio = audio.mean(axis=1)
        return audio.astype(np.float32)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Backend 2: Additive synthesis (no external deps)
# ---------------------------------------------------------------------------

def _synthesize_additive(midi_path: str, sample_rate: int = 22050) -> np.ndarray:
    """Pure-Python additive synthesis — sine wave per note with ADSR envelope."""
    import pretty_midi
    pm = pretty_midi.PrettyMIDI(str(midi_path))
    duration = pm.get_end_time() + 0.5
    n_samples = int(duration * sample_rate)
    audio = np.zeros(n_samples, dtype=np.float64)

    for instrument in pm.instruments:
        if instrument.is_drum:
            continue
        for note in instrument.notes:
            start = int(note.start * sample_rate)
            end   = min(int(note.end * sample_rate), n_samples)
            if start >= end:
                continue

            freq = 440.0 * 2 ** ((note.pitch - 69) / 12.0)
            n    = end - start
            t    = np.arange(n) / sample_rate

            # Fundamental + 2 harmonics for richness
            wave = (
                np.sin(2 * np.pi * freq * t) * 0.6
                + np.sin(2 * np.pi * 2 * freq * t) * 0.25
                + np.sin(2 * np.pi * 3 * freq * t) * 0.10
            )

            # Simple ADSR-like envelope
            attack_s  = min(0.01, n / sample_rate * 0.1)
            release_s = min(0.15, n / sample_rate * 0.4)
            a_samp = int(attack_s  * sample_rate)
            r_samp = int(release_s * sample_rate)
            env = np.ones(n)
            if a_samp > 0:
                env[:a_samp] = np.linspace(0, 1, a_samp)
            if r_samp > 0:
                env[-r_samp:] *= np.linspace(1, 0, r_samp)

            amp = (note.velocity / 127.0) * 0.25
            audio[start:end] += wave * env * amp

    # Normalize
    peak = np.abs(audio).max()
    if peak > 1e-6:
        audio = audio / peak * 0.90
    return audio.astype(np.float32)


# ---------------------------------------------------------------------------
# Optional: EnCodec neural polish
# ---------------------------------------------------------------------------

def _encodec_polish(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    """Pass audio through EnCodec encoder-decoder for neural quality improvement."""
    try:
        import torch
        from encodec import EncodecModel
        from encodec.utils import convert_audio

        model = EncodecModel.encodec_model_24khz()
        model.set_target_bandwidth(6.0)
        model.eval()

        wav = torch.from_numpy(audio).float().unsqueeze(0).unsqueeze(0)  # (1,1,T)
        wav = convert_audio(wav, sample_rate, model.sample_rate, model.channels)

        with torch.no_grad():
            encoded = model.encode(wav)
            decoded = model.decode(encoded[0], encoded[1])

        out = decoded.squeeze().numpy()
        # Resample back to original sample_rate if needed
        if model.sample_rate != sample_rate:
            import librosa
            out = librosa.resample(out, orig_sr=model.sample_rate, target_sr=sample_rate)
        return out.astype(np.float32)

    except ImportError:
        print("  encodec not installed — skipping neural polish. pip install encodec")
        return audio
    except Exception as e:
        print(f"  EnCodec polish failed: {e}")
        return audio


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def synthesize_midi(midi_path, wav_path, sample_rate=44100, use_encodec=False):
    """Render a MIDI file to WAV.

    Tries FluidSynth first, falls back to additive synthesis.
    Optionally applies EnCodec encoder-decoder as a neural quality pass.

    Returns the path to the written WAV file.
    """
    import soundfile as sf

    midi_path = Path(midi_path)
    wav_path  = Path(wav_path)
    wav_path.parent.mkdir(parents=True, exist_ok=True)

    # Try FluidSynth first
    audio = _synthesize_fluidsynth(str(midi_path), sample_rate)
    backend = "FluidSynth"
    if audio is None:
        audio = _synthesize_additive(str(midi_path), sample_rate)
        backend = "additive"
    print(f"  Synthesized via {backend} ({len(audio)/sample_rate:.1f}s, {sample_rate}Hz)")

    if use_encodec:
        print("  Applying EnCodec neural polish...")
        audio = _encodec_polish(audio, sample_rate)

    sf.write(str(wav_path), audio, sample_rate)
    print(f"  Saved: {wav_path}")
    return wav_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Synthesize Apollo-generated MIDI to WAV")
    parser.add_argument("--midi",        type=str, required=True,  help="MIDI file or directory")
    parser.add_argument("--output-dir",  type=str, default=None,   help="Output directory (default: same as MIDI)")
    parser.add_argument("--sample-rate", type=int, default=44100,  help="Output sample rate")
    parser.add_argument("--encodec",     action="store_true",      help="Apply EnCodec neural polish")
    parser.add_argument("--all",         action="store_true",      help="Process all .mid files in directory")
    args = parser.parse_args()

    midi_path = Path(args.midi)

    if args.all or midi_path.is_dir():
        files = sorted(midi_path.glob("*.mid")) + sorted(midi_path.glob("*.midi"))
        print(f"Processing {len(files)} MIDI files...")
    else:
        files = [midi_path]

    for f in files:
        out_dir = Path(args.output_dir) if args.output_dir else f.parent
        wav_path = out_dir / f.with_suffix(".wav").name
        print(f"\n{f.name}")
        synthesize_midi(f, wav_path, sample_rate=args.sample_rate, use_encodec=args.encodec)


if __name__ == "__main__":
    main()

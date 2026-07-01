# Synth-Independent Rendering (no Ableton)

Validated path for replacing manual Ableton/Operator `call.wav` bounces with a headless,
deterministic, pure-Python renderer feeding Apollo's existing mel-conditioning contract.

## Validated Patterns

### 1. DawDreamer + Faust FM renders MIDI → audio headlessly on Apple Silicon
- `dawdreamer==0.8.3` installs from a prebuilt **arm64 / Python 3.11 wheel** in ~5s. No
  JUCE/Faust build toolchain, no Docker. (`uv pip install dawdreamer numpy soundfile`.)
- A 2-operator FM patch as a compiled Faust DSP string, driven by MIDI notes, where
  `ratio`/`index` are the timbre knobs (the FM analogue of an Operator preset):

```python
import dawdreamer as dd
SR, BLOCK = 44100, 512
FM_DSP = """
import("stdfaust.lib");
freq  = hslider("freq",  440, 20, 20000, 0.01);
gain  = hslider("gain",  0.5,  0,     1, 0.01);
gate  = button("gate");
ratio = hslider("ratio", 2.0, 0.5,   12, 0.01);
index = hslider("index", 2.0, 0.0,   12, 0.01);
env   = en.adsr(0.005, 0.12, 0.7, 0.2, gate);
mod   = os.osc(freq * ratio) * index * freq;
process = os.osc(freq + mod) * env * gain <: _,_;
"""
engine = dd.RenderEngine(SR, BLOCK)
synth = engine.make_faust_processor("fm")
synth.set_dsp_string(FM_DSP)
synth.num_voices = 8                  # polyphony so overlapping releases don't cut
synth.set_parameter(1, ratio)         # NOTE: integer index, not path string (see Landmines)
synth.set_parameter(0, index)
synth.add_midi_note(60, 100, 0.0, 0.30)  # pitch, velocity, start_s, dur_s
engine.load_graph([(synth, [])])
engine.render(1.5)                     # seconds — matches Apollo's 0.5–1.5s gesture
audio = engine.get_audio()             # (channels, samples); write with soundfile (audio.T)
```

- **Determinism:** re-rendering the same patch + MIDI is **bit-for-bit identical**
  (`np.array_equal` true). Essential for reproducible training data.

### 2. The mel path is a drop-in source swap — zero pipeline change
- Apollo's production `apollo.ingest.audio.MelExtractor` (COND-01: 22050 Hz, n_fft=2048,
  hop=512, n_mels=128, log, fixed `(96,128)`) consumes the FM-rendered WAV untouched.
- The mel is deterministic and **timbre-discriminable**: two FM presets gave
  `cos(A,B)=0.85` across-preset vs `1.00` within-preset, `L2=783`, and a ~2.9-unit
  mean-log-mel gap (brighter preset reads higher). That's the learnable signal the mel
  encoder needs.

```python
from apollo.ingest.audio import MelExtractor
mx = MelExtractor()
log_mel = mx("call.wav", "data/pairs/001")   # torch.float32, shape (96, 128)
```

## Landmines

- **Faust param paths are mangled under polyphony.** With `num_voices` set, params appear as
  `/Polyphonic/Voices/dawdreamer/<name>` and `set_parameter("<path>", v)` **fails with
  RuntimeError**. Use `set_parameter(<int index>, v)` — get indices from
  `synth.get_parameters_description()`. `freq`/`gain`/`gate` are consumed by the MIDI layer
  and are NOT settable params.
- **Benign warning** `undefined symbol : effect` is printed by the poly factory (no effect
  chain declared). Harmless — filter it from logs.
- **Output clips.** Peaks exceeded 1.0 (1.13–1.19); `soundfile` clips to [-1,1] for PCM. A
  normalization / headroom stage is required before writing WAV, or the mel sees clipped
  audio.
- **No `dawdreamer.__version__`** — don't use it for version checks.

## Constraints

- Requires Python 3.11 (matches Apollo's `requires-python >=3.11`); wheel is macOS arm64.
- The spike used an **isolated** venv for DawDreamer (heavy wheel) + numpy + soundfile.
  Spike 002 used the **project** venv (torch 2.12 / torchaudio 2.11) to import `apollo`.
  DawDreamer is not currently a project dependency.
- **Fidelity is unproven and out of scope.** No `data/pairs/NNN/call.wav` exists yet, so
  there was no head-to-head against real Operator audio. The open decision is product, not
  technical:
  - (a) reimplement Operator's 4-op / 11-algorithm topology in Faust for sound identity, or
  - (b) adopt a controllable FM family as the v1 timbre space — REQUIREMENTS.md already
    contemplates "v1 timbre space constrained to one FM family so mel-conditioning is
    learnable on a small corpus."
- **Train/serve consistency:** whatever renders training `call.wav` must also render
  inference-time calls (same Faust patch + params) or the mel distribution shifts.

## Origin
Synthesized from spikes: 001, 002
Source files available in: sources/001-dawdreamer-fm-render/, sources/002-fm-mel-conditioning/

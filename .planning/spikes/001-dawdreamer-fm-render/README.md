---
spike: 001
name: dawdreamer-fm-render
validates: "Given a fresh venv on Apple Silicon, when we install DawDreamer and render a MIDI phrase through a Faust 2-op FM engine, then we get a deterministic call.wav with timbre controlled by FM params — no Ableton"
verdict: VALIDATED
related: [002]
tags: [dawdreamer, faust, fm-synth, rendering, cond, no-ableton]
---

# Spike 001: DawDreamer FM Render

## What This Validates

**Given** a fresh Python 3.11 venv on Apple Silicon (arm64),
**when** we `pip install dawdreamer` and render a short MIDI "call" phrase through a
Faust 2-operator FM patch,
**then** we get a deterministic `call.wav` whose timbre is controlled by FM parameters
(`ratio`, `index`) — with **no Ableton / Operator in the loop**.

This is the highest-risk question in the Operator-replacement research (option 1): the
install on macOS arm64 and the existence of a usable headless FM engine are the
make-or-break.

## How to Run

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python dawdreamer numpy soundfile
.venv/bin/python render_fm.py
```

## What to Expect

Three WAVs written and a printed report:
- `callA_ratio2_index2.wav`, `callB_ratio3_index8.wav` — two contrasting FM timbres.
- `determinism: identical=True maxdiff=0.00e+00` — re-rendering preset A is bit-identical.
- `A vs B differ: maxdiff >> 0` — changing FM params measurably changes the audio.
- `VERDICT: PASS`.

## Results

**VERDICT: VALIDATED ✓**

```
callA_ratio2_index2.wav: shape=(2, 66150) peak=1.1291 rms=0.27424
callB_ratio3_index8.wav: shape=(2, 66150) peak=1.1906 rms=0.40146
determinism: identical=True maxdiff=0.00e+00
A vs B differ: maxdiff=2.2008
VERDICT: PASS
```

Evidence:
- **Install is trivial.** `dawdreamer==0.8.3` installs from a prebuilt wheel on arm64 /
  Python 3.11 in ~5s. No JUCE/Faust build toolchain needed, no Docker.
- **Render is deterministic.** Re-rendering the same patch + MIDI is bit-for-bit identical
  (`maxdiff=0.0`) — critical for reproducible training data and train/serve consistency.
- **Timbre tracks FM params.** ratio 2/index 2 vs ratio 3/index 8 produce audibly and
  numerically different output (`maxdiff=2.2`), and different RMS — the FM knobs are the
  analogue of an Operator preset.
- **No Ableton.** Pure Python; the only dependency is the DawDreamer wheel + Faust DSP
  string compiled in-process.

### Surprises / gotchas (signal for the build)
- **Faust param paths are mangled under polyphony.** With `num_voices` set, params are
  exposed as `/Polyphonic/Voices/dawdreamer/<name>`, and `set_parameter(path)` by string
  **failed** — only `set_parameter(index, value)` (integer index from
  `get_parameters_description()`) worked. Use integer indices.
- **Benign warning:** `undefined symbol : effect` is printed by the poly factory (no
  effect chain declared). Harmless; filter it from logs.
- **Output clips.** Peaks were >1.0 (1.13, 1.19); `soundfile` clips to [-1,1] for PCM.
  The real renderer needs a headroom/normalization stage before writing WAV.
- **`dawdreamer.__version__` does not exist** — don't rely on it for version checks.

### Scope note
This validates the *renderer path*, not Operator fidelity. A literal head-to-head against
Operator-bounced audio is out of scope here (no `data/pairs/NNN/call.wav` exists yet) and
belongs to the corpus-substitution decision in the research write-up. The 2-op FM patch is
a stand-in; matching Operator's 4-op / 11-algorithm topology is more Faust, not a new risk.

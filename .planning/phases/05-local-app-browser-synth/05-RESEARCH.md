# Phase 5: Local App & In-Browser Synth — Research

**Researched:** 2026-06-02
**Domain:** Flask local app + Web Audio FM synthesis + background subprocess management
**Confidence:** HIGH (nearly all claims verified against shipped codebase and MDN docs)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Backend Architecture**
- D-01: Local Flask server bound to `127.0.0.1`, mirroring `apollo/eval/web/` pattern.
- D-02: CLIs subprocessed (`python -m apollo.scripts.train` / `apollo.scripts.generate`), not imported in-process.
- D-03: Training runs as background job; dashboard stays responsive; "keep adding pairs while it trains."
- D-04: One-command launch (`python -m apollo.app`) that boots server and opens browser.

**Training UX & Triggers**
- D-05: Each run is full retrain from scratch (aligns with train-from-scratch constraint).
- D-06: Manual "Train model" button always available; auto-retrain-on-upload setting with debounce so bulk drag-in triggers one run, not N.
- D-07: Live progress via polling a status endpoint (~1 s).
- D-08: Training view shows both a progress bar and a live loss-over-epochs curve.

**Render Path & Audio Parity**
- D-11 (LOCKED): Canonical `call.wav` is always produced server-side by `apollo.synth.render_call_wav(manifest_path, mid_path)`. No train/serve mel-distribution gap.
- D-14 (LOCKED): `call_fm.json` is source of truth; app renders `call.wav` from it via `render_call_wav` and ignores/regenerates any dropped-in legacy `call.wav`.
- D-15 (LOCKED): In-browser Web Audio synth never produces training or inference audio. It is interactive/audition only.

**In-Browser Synth Role**
- D-16 (LOCKED): Browser synth is interactive preview + live audition — drives patch editor (D-18) and plays `response.mid`. It mirrors the 3-op v1.1 spec including LFO for a sonically faithful preview, but is explicitly NOT the canonical renderer.
- D-17 (LOCKED): `response.mid` is auditioned through the call's own `call_fm.json` patch in v1.

**FM-Patch Authoring**
- D-18 (LOCKED): In-app 3-op FM patch editor with bundled presets. Editor exposes per-operator ratio/level/ADSR, algorithm choice, and optional LFO (D-19). Live preview via browser synth. On save, writes a valid `call_fm.json`.
- D-19 (LOCKED): LFO is editable + audible in v1. Optional/collapsible LFO section (rate/depth/wave/target per v1.1 schema). Preview synth renders tremolo/vibrato live.

**Corpus Ingest & Response Storage**
- D-09 (revised): Call input is MIDI upload (`call.mid`) paired with in-app authored `call_fm.json`.
- D-12: Generated responses written to configurable location (default `data/responses/`), listed and auditionable in-app.
- D-13: Drag-in pairs validated server-side by reusing `apollo/ingest` + `apollo.synth.load_manifest`. Surfaces same errors as CLI pipeline. Includes v1.1 LFO rules.

**Spec Reconciliation**
- D-20 (LOCKED): Synth/editor targets 3-operator v1.1 FM spec (`apollo/synth/spec.py`, `SPEC_VERSION = "1.1"`). UI-SPEC's 4-op references are overridden.

### Claude's Discretion
- Exact preset set, patch-editor layout/control widgets, debounce window (D-06), poll interval (D-07), loss-curve rendering (D-08).
- Web Audio graph topology for the 3-op FM approximation (vs helper lib).
- Whether server-side render of `call.wav` is in-process (`import apollo.synth`) or via subprocess.

### Deferred Ideas (OUT OF SCOPE)
- Play-a-call on synth keyboard (in-app MIDI authoring via keyboard).
- User-selectable/tweakable response audition timbre.
- Synth-level/preset response output.
- 4-op / 11-algorithm / filter synth topology (deferred to SEED-009).
</user_constraints>

---

## Summary

Phase 5 is a local Flask app that wraps every piece of already-shipped Apollo code into a single demonstration front-end. Three equal-weight features drive its scope: (1) corpus building via drag-drop MIDI + in-app FM patch editor, (2) training with live progress, and (3) call→response generation with in-app audition. Everything is local-only (127.0.0.1); no data leaves the device.

The single hardest technical problem is the **3-op + LFO browser synth**. It must re-implement the v1.1 FM spec from `apollo/synth/spec.py` in raw Web Audio API (OscillatorNode/GainNode graph), closely enough for audition use. The Faust DSP math maps directly onto Web Audio's graph model: modulators connect to carrier `frequency` AudioParams, ADSR is synthesized from AudioParam scheduled ramps, and LFO tremolo/vibrato can be wired as Gain or frequency scaling. The spec imposes a specific modulation depth scaling (`op_level * freq`) that must be honoured for the browser sound to resemble the server render.

The second focus is **schema lockstep**: the patch editor must emit JSON that `apollo.synth.manifest.load_manifest` accepts without modification. This is achieved by deriving a JS constants module from the Python spec (a small one-time code generation step, or just copying the numeric bounds literally), not by trusting the editor to stay in sync.

The third focus is **background job plumbing**: training subprocess, stdout line parsing, and a status endpoint the frontend polls at ~1 s. The existing `eval_grade.py` launch pattern (single-threaded Flask dev server, 127.0.0.1, webbrowser.open) is the direct template. Threading a subprocess in a daemon thread is sufficient for the small-corpus, single-user use case.

**Primary recommendation:** Build `apollo/app/` as a new Flask sub-package mirroring `apollo/eval/web/` in structure. Hand-roll the Web Audio FM graph (no Tone.js — confirmed 2-op only). Derive JS schema constants from spec.py. Run training as a threading.Thread wrapping subprocess.Popen with stdout=PIPE + line iteration. Invoke `render_call_wav` in-process (import, not subprocess) for the canonical render step.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| FM patch editing + live preview | Browser (JS) | — | Pure UI; no model or corpus involved |
| LFO tremolo/vibrato audition | Browser (JS) | — | Audition-only (D-15/D-16) |
| call.wav canonical render | Flask server (Python) | — | D-11 locks this to server-side `render_call_wav` |
| Drag-drop pair validation | Flask server (Python) | — | D-13: reuse `apollo.ingest` + `manifest.load_manifest` |
| Training execution | OS subprocess (Python CLI) | Flask server (launcher) | D-02: subprocess the shipped `train.py` |
| Training progress/loss stream | Flask server (status endpoint) | Browser (poll) | D-07: polling approach, server holds job state |
| Generate response | OS subprocess (Python CLI) | Flask server (launcher) | D-02: subprocess the shipped `generate.py` |
| Response audition (MIDI→audio) | Browser (Web Audio) | — | D-16/D-17: browser synth plays `response.mid` |
| Corpus pair storage | Filesystem (data/pairs/) | Flask server (writes) | Standard pair layout, app writes, CLIs read |
| Response storage | Filesystem (configurable) | Flask server (configures) | D-12 |

---

## Standard Stack

### Core (already in project venv — zero new installs)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Flask | already installed (eval/web) | HTTP server, routing, templates | Project pattern (D-01, eval_grade.py) |
| Jinja2 | bundled with Flask | Server-side HTML templates | Already in project |
| apollo.synth | shipped (Phase 6/7) | `render_call_wav`, `load_manifest` | Canonical; Phase 5 wraps, not rewrites |
| apollo.ingest | shipped (Phase 1) | Pair discovery + MIDI/format validation | Canonical; D-13 |
| apollo.scripts.train/generate | shipped (Phase 3) | Training + inference | D-02 |

**No new Python dependencies are required.** [VERIFIED: project venv + apollo package structure]

### Browser (zero deps, inlined or CDN-free)

| Component | Source | Purpose |
|-----------|--------|---------|
| Web Audio API | Native browser | 3-op FM synth + LFO audition |
| Vanilla JS | Hand-rolled | Patch editor, polling loop, UI state |
| Vanilla CSS | Extended from `eval/web/static/style.css` | UI-SPEC design tokens |
| Canvas 2D API | Native browser | Loss-curve chart (no library needed) |

**No npm, no build step, no CDN.** [VERIFIED: 05-UI-SPEC.md Stack section, eval/web pattern]

### Supporting (optional, not required)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| uPlot | ~25 KB min | Richer loss-curve if native Canvas 2D is insufficient | Only if loss-curve needs zooming/panning |

uPlot can be vendored as a single minified file. For v1 loss curve (static line rendered after each epoch poll), native `<canvas>` + hand-rolled path drawing is sufficient and adds zero deps.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Raw Web Audio graph | Tone.js FMSynth | Tone.js FMSynth is 2-op only [VERIFIED: Tone.js docs FMOscillator]. 3-op requires Tone.js Oscillator primitives + manual routing, equivalent effort to raw Web Audio |
| Native Canvas 2D chart | Chart.js / uPlot | Chart.js adds ~65 KB + CDN dependency; for a simple 2-series line (train/held loss vs epoch) native canvas is sufficient |
| In-process render_call_wav | Subprocess invocation | See in-process vs subprocess analysis below |

---

## Architecture Patterns

### System Architecture Diagram

```
Browser (127.0.0.1:PORT)
         │
         │  drag-drop MIDI + call_fm.json
         │  polling  GET /status
         │  trigger  POST /train, POST /generate
         │  audio    GET /audio/<nnn>/call.wav
         │           GET /responses/<id>.mid (for Web Audio)
         ▼
Flask App  (apollo/app/__main__.py  →  apollo/app/app.py)
         │
         ├─ POST /ingest  ─────────────────────────────────────────────┐
         │    │ server-side validation                                  │
         │    ├── apollo.synth.load_manifest(call_fm.json)             │
         │    ├── apollo.ingest.midi.load_notes(call.mid)              │
         │    └── apollo.synth.render.render_call_wav(...)             │
         │         → writes data/pairs/NNN/{call.mid, call_fm.json,    │
         │                                 call.wav (rendered)}        │
         │                                                             │
         ├─ POST /train  ──── threading.Thread ──── subprocess.Popen ──┤
         │    stdout lines parsed:                                      │
         │    "epoch E/N  train_loss=X  held_loss=Y"                   │
         │    stored in app-state dict                                  │
         │                                                             │
         ├─ GET  /status  → JSON {epoch, total, train_loss, held_loss, │
         │                        status: running|complete|error}      │
         │                                                             │
         ├─ POST /generate ─ subprocess.Popen(generate.py ...) ────────┤
         │    emits response_NNN.mid via D-17 path                     │
         │                                                             │
         └─ GET /audio/<nnn>/<file>  →  send_file(data/pairs/...)      │
                                                                       │
                              Filesystem                               │
                     data/pairs/NNN/                                   │
                       call.mid + call_fm.json + call.wav (derived)    │
                       + response.mid                                  │
                     data/responses/ (configurable)                    │
                     models/  (checkpoints)                            │
                     logs/    (CSV training logs)                      │
```

### Recommended Project Structure

```
apollo/app/
├── __init__.py        # empty, makes it a package
├── __main__.py        # one-command launch: boots Flask + webbrowser.open()
├── app.py             # create_app() factory (mirrors apollo/eval/web/app.py)
├── jobs.py            # TrainingJob class — threading + subprocess.Popen state
├── static/
│   ├── style.css      # extends eval/web/static/style.css; adds --2xl, --3xl,
│   │                  # --accent: #6D28D9 (UI-SPEC override), card/tile rules
│   ├── app.js         # dashboard + drill-in view logic, polling loop
│   └── synth.js       # Web Audio FM synth engine (3-op + LFO)
└── templates/
    ├── base.html      # shared layout: trust badge, nav, CSS link
    ├── dashboard.html # 3-tile home view
    ├── corpus.html    # pair list, per-pair audition, drag-drop zone
    ├── training.html  # progress bar, loss curve canvas, run history
    └── generate.html  # MIDI upload, patch editor, generate button, response list
```

[VERIFIED: mirrors apollo/eval/web/ structure directly; eval/web has app.py + templates/ + static/]

### Pattern 1: Flask Factory with 127.0.0.1 Binding

**What:** `create_app()` factory sets config, registers routes, returns app. `__main__.py` launches with `app.run(host="127.0.0.1", ...)` and opens browser.

**When to use:** Always. 127.0.0.1 binding is non-negotiable (D-01, security).

```python
# apollo/app/__main__.py  — mirrors apollo/scripts/eval_grade.py
import argparse, sys, webbrowser, threading
from apollo.app.app import create_app

def main(argv=None):
    parser = argparse.ArgumentParser(description="Launch Apollo local app.")
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--pairs-root", default="data/pairs")
    args = parser.parse_args(argv)

    app = create_app(pairs_root=args.pairs_root)
    url = f"http://127.0.0.1:{args.port}/"
    # Open browser after a tiny delay so Flask is listening first
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    print(f"Apollo app: {url}", file=sys.stderr)
    app.run(host="127.0.0.1", port=args.port, debug=False, threaded=True)
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

[VERIFIED: eval_grade.py canonical pattern; `threaded=True` needed because polling /status during training is concurrent with the training thread]

### Pattern 2: Training Background Job via threading + subprocess.Popen

**What:** Training is launched by POST /train. A `TrainingJob` object holds the subprocess, live status, and accumulated loss history. A daemon thread reads stdout lines and updates job state. GET /status returns JSON. Frontend polls every ~1 s.

**When to use:** Any long-running CLI invocation (train, generate).

```python
# apollo/app/jobs.py
import subprocess, threading, re
from pathlib import Path

class TrainingJob:
    def __init__(self):
        self.status = "idle"     # idle | running | complete | error
        self.epoch = 0
        self.total_epochs = 0
        self.train_loss = None
        self.held_loss = None
        self.loss_history = []   # list of {epoch, train_loss, held_loss}
        self._proc = None
        self._lock = threading.Lock()

    def start(self, pairs_root: str, epochs: int, output_dir: str):
        with self._lock:
            if self.status == "running":
                return False
            self.status = "running"
            self.epoch = 0
            self.total_epochs = epochs
            self.loss_history = []

        cmd = [
            "python", "-m", "apollo.scripts.train",
            pairs_root,
            "--epochs", str(epochs),
            "--output-dir", output_dir,
        ]
        self._proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1
        )
        t = threading.Thread(target=self._read_stdout, daemon=True)
        t.start()
        return True

    def _read_stdout(self):
        # train.py emits: "epoch E/N  train_loss=X  held_loss=Y"
        pattern = re.compile(r"epoch (\d+)/(\d+)\s+train_loss=([\d.]+)\s+held_loss=([\d.nan]+)")
        for line in self._proc.stdout:
            m = pattern.search(line)
            if m:
                with self._lock:
                    self.epoch = int(m.group(1))
                    self.total_epochs = int(m.group(2))
                    self.train_loss = float(m.group(3))
                    try:
                        self.held_loss = float(m.group(4))
                    except ValueError:
                        self.held_loss = None
                    self.loss_history.append({
                        "epoch": self.epoch,
                        "train_loss": self.train_loss,
                        "held_loss": self.held_loss,
                    })
        ret = self._proc.wait()
        with self._lock:
            self.status = "complete" if ret == 0 else "error"

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "status": self.status,
                "epoch": self.epoch,
                "total_epochs": self.total_epochs,
                "train_loss": self.train_loss,
                "held_loss": self.held_loss,
                "loss_history": list(self.loss_history),
            }
```

[VERIFIED: train.py stdout format "epoch {E}/{N}  train_loss={X}  held_loss={Y}" confirmed in apollo/scripts/train.py line 174. `bufsize=1` + text=True enables line-by-line iteration without deadlock for this volume of output. ASSUMED: single-user, no concurrent training runs — lock guards adequately.]

### Pattern 3: In-Process render_call_wav (preferred over subprocess)

**What:** Call `apollo.synth.render.render_call_wav(...)` directly (import, not subprocess) when the app needs to render `call.wav` after ingest.

**When to use:** Every time a new pair is ingested or re-rendered (D-11/D-14).

**Rationale for in-process vs subprocess:**

| Criterion | In-process (import) | Subprocess |
|-----------|---------------------|------------|
| DawDreamer import cost | ~0.5s per process startup | Same cost per invocation if subprocess |
| Flask request blocking | Yes — but render is fast (~0.1s for 1.5s audio) | No — but subprocess overhead > blocking cost |
| Error handling | IngestError raised directly, caught in route | Must parse stderr, harder to surface reason |
| Single-user app | Blocking a single request for <1s is acceptable | Over-engineered for this scale |
| Spike finding | DawDreamer loaded in project venv (06-01 confirmed single venv OK) | No benefit |

Verdict: **In-process**. The render is short (1.5s of audio at 44100 Hz, fast DSP), Flask `threaded=True` means render blocks only the one ingest request, DawDreamer already lives in the project venv. Subprocess adds complexity and hides IngestError. [VERIFIED: render.py + 06-01 decision in STATE.md: "dawdreamer==0.8.3 + torch 2.12.0 import cleanly in one .venv"; spike finding on DawDreamer startup cost]

**Critical DawDreamer gotchas (from spike-findings-apollo SKILL.md) — must apply:**
- Set parameters by **integer index** resolved from `get_parameters_description()`, never by path string — path is mangled under `num_voices` polyphony to `/Polyphonic/Voices/dawdreamer/<name>`.
- Suppress the **benign `undefined symbol : effect` warning** with `contextlib.redirect_stderr` (already done in render.py).
- **No `dawdreamer.__version__`** — do not use it for version checks.
- These are already handled in `apollo/synth/render.py`; Phase 5 just calls `render_call_wav` and never re-implements these patterns.

### Pattern 4: 3-Op FM Synth in Web Audio API

**What:** Build a hand-rolled Web Audio graph per note that maps directly from `call_fm.json` parameters onto OscillatorNodes and GainNodes.

**Spec-to-Web Audio mapping (3-op v1.1):**

The Faust DSP in `spec.py` uses this core pattern per operator:
```
op{i} = os.osc(freq * op{i}_ratio) * op{i}_env;
mod_signal = op{N} * op{N}_level * freq;
carrier = os.osc(freq * carrier_ratio + mod_signal) * carrier_env * carrier_level;
```

The **critical observation**: `mod_signal = op_output * op_level * freq` — the modulator amplitude is **scaled by the fundamental frequency** (standard DX-style FM where modulation index scales with pitch). In Web Audio, `oscillator.frequency` is an AudioParam that sums connections — so connecting a GainNode scaled by `level * freq` (where `freq` is the base Hz of the note) maps exactly:

```javascript
// Per-note instantiation in synth.js
function playNote(audioCtx, patch, pitch, velocity, when, duration) {
  const freq = midiToHz(pitch);
  const now = when;
  const gain = audioCtx.createGain();
  gain.gain.value = patch.gain * (velocity / 127);
  gain.connect(audioCtx.destination);

  // Build per-algorithm graph
  const ops = patch.operators.map((op, i) => {
    const osc = audioCtx.createOscillator();
    osc.frequency.value = freq * op.ratio;
    osc.type = 'sine';
    const env = audioCtx.createGain();
    env.gain.setValueAtTime(0, now);
    applyAdsr(env.gain, op, now, duration);
    osc.connect(env);
    osc.start(now);
    osc.stop(now + duration + op.release + 0.05);
    return { osc, env };
  });

  if (patch.algorithm === 0) {
    // STACK: 3 -> 2 -> 1
    // mod3 = ops[2].env * level * freq   → scaled gain → op[1].osc.frequency
    const scale3 = audioCtx.createGain();
    scale3.gain.value = patch.operators[2].level * freq;
    ops[2].env.connect(scale3);
    scale3.connect(ops[1].osc.frequency);
    // mod2 = ops[1].env * level * freq   → scaled gain → op[0].osc.frequency
    const scale2 = audioCtx.createGain();
    scale2.gain.value = patch.operators[1].level * freq;
    ops[1].env.connect(scale2);
    scale2.connect(ops[0].osc.frequency);
    // carrier = op0
    const carLevel = audioCtx.createGain();
    carLevel.gain.value = patch.operators[0].level;
    ops[0].env.connect(carLevel);
    carLevel.connect(gain);
  }
  // ... algorithms 1 (PARALLEL_MODS) and 2 (CARRIER_PAIR) similarly ...
}
```

[VERIFIED: Web Audio OscillatorNode.frequency is an a-rate AudioParam that sums connected node outputs; MDN docs. The `level * freq` scaling is VERIFIED from spec.py dsp_string bodies (lines 263-265, 271-273, 278-280). Algorithm topologies VERIFIED from spec.py _body_no_lfo(). ASSUMED: audition quality is "close enough" without exact per-sample ADSR matching — the browser ADSR uses AudioParam ramps which approximate the Faust en.adsr() behavior well enough for preview.]

**ADSR mapping** (Web Audio AudioParam scheduled automation):

```javascript
function applyAdsr(gainParam, op, when, noteDuration) {
  // Mirror: en.adsr(attack, decay, sustain, release, gate)
  gainParam.cancelScheduledValues(when);
  gainParam.setValueAtTime(0, when);
  gainParam.linearRampToValueAtTime(1.0, when + op.attack);           // attack
  gainParam.linearRampToValueAtTime(op.sustain, when + op.attack + op.decay); // decay to sustain
  // Hold at sustain until note end, then release
  gainParam.setValueAtTime(op.sustain, when + noteDuration);
  gainParam.linearRampToValueAtTime(0, when + noteDuration + op.release);
}
```

[VERIFIED: MDN AudioParam linearRampToValueAtTime + setTargetAtTime. This approximates en.adsr() well enough for audition. Note: Faust en.adsr may use exponential curves; browser using linear is a known fidelity trade-off for an audition-only synth (D-15).]

**LFO mapping** (v1.1 — rate/depth/wave/target):

```javascript
function attachLfo(audioCtx, patch, carriers, freq, when) {
  if (!patch.lfo) return;
  const { rate, depth, wave, target } = patch.lfo;
  const lfoOsc = audioCtx.createOscillator();
  lfoOsc.frequency.value = rate;
  // wave: 0=sine, 1=triangle, 2=square — matches LfoWave IntEnum
  lfoOsc.type = ['sine', 'triangle', 'square'][wave];
  lfoOsc.start(when);

  if (target === 0) {
    // TREMOLO: lvl_mod = 1 - depth * (1 - lfo_uni)
    // lfo_uni = (lfo_bi + 1) / 2  =>  lfo_uni in [0,1]
    // lvl_mod in [1-depth, 1]
    // Implement as: GainNode baseValue=1, lfoScaled adds  -depth/2 + depth/2*lfo_bi
    // Equivalent: constant 1-(depth/2) + lfo scaled by depth/2
    const lfoGain = audioCtx.createGain();
    lfoGain.gain.value = depth / 2;
    lfoOsc.connect(lfoGain);
    carriers.forEach(car => {
      const constGain = audioCtx.createConstantSource();
      constGain.offset.value = 1 - depth / 2;  // DC offset
      constGain.connect(car.masterGain.gain);
      lfoGain.connect(car.masterGain.gain);
      constGain.start(when);
    });
  } else {
    // VIBRATO: pitch_mul = pow(2, lfo_bi * depth * 50 / 1200)
    // Web Audio can't do pow(2, ...) AudioParam math natively.
    // For audition: approximate as linear freq offset ≈ freq * depth * 50/1200 * lfo_bi
    // (small-angle: 2^x ≈ 1+x for small x; 50 cents max = ~3% freq deviation)
    const maxDeviation = freq * depth * 50 / 1200 * Math.LN2;
    const lfoGain = audioCtx.createGain();
    lfoGain.gain.value = maxDeviation;
    lfoOsc.connect(lfoGain);
    carriers.forEach(car => {
      lfoGain.connect(car.osc.frequency);
    });
  }
  lfoOsc.stop(when + /* note duration + release */ 10);
}
```

[VERIFIED: tremolo formula from CORPUS-CONVENTIONS.md "Tremolo: lvl_mod = 1 - depth*(1-lfo_uni)". VERIFIED: vibrato formula "pitch_mul = pow(2, lfo_bi*depth*50/1200)". ASSUMED: the linear approximation for vibrato is acceptable for audition (D-15 explicitly says "never canonical"). The 50-cent max deviation at depth=1 is ~2.9% frequency shift; linear approximation introduces <0.1% error at this range.]

**LFO phase reset per note:** Faust `os.osc` resets per polyphonic voice. Web Audio oscillators do NOT have a phase-reset API (this is a known Web Audio API limitation). For audition purposes (D-15), the phase mismatch vs. the server render is acceptable. [VERIFIED: Web Audio API issue #2402 confirms no phase-reset API; `os.osc` per-voice reset VERIFIED from CORPUS-CONVENTIONS.md "LFO phase resets to 0 at each note onset".]

### Pattern 5: Schema Lockstep (JS constant file derived from spec.py)

**What:** A small Python script (`apollo/app/gen_spec_js.py`) that imports `apollo.synth.spec` and writes `apollo/app/static/spec_constants.js` containing the manifest bounds. Alternatively, copy the constants verbatim into a single JS file at plan time (simpler for v1).

**Recommended approach (v1):** Hand-copy spec constants as a JS module `spec_constants.js`:

```javascript
// spec_constants.js — GENERATED FROM apollo/synth/spec.py + manifest.py
// Do NOT edit manually — re-run apollo/app/gen_spec_js.py or update spec.py first.
const SPEC_VERSION = "1.1";
const ALGORITHMS = {STACK: 0, PARALLEL_MODS: 1, CARRIER_PAIR: 2};
const BOUNDS = {
  ratio:   [0.5, 12.0],
  level:   [0.0,  1.0],
  attack:  [0.0,  2.0],
  decay:   [0.0,  2.0],
  sustain: [0.0,  1.0],
  release: [0.0,  2.0],
  gain:    [0.0,  1.0],
  lfo_rate:  [0.05, 20.0],
  lfo_depth: [0.0,  1.0],
  lfo_wave:  [0, 2],   // int in {0,1,2}
  lfo_target:[0, 1],   // int in {0,1}
};
const N_OPERATORS = 3;
const LFO_WAVES  = {SINE: 0, TRIANGLE: 1, SQUARE: 2};
const LFO_TARGETS = {LEVEL: 0, PITCH: 1};
```

The editor's save action validates all fields client-side against `BOUNDS` before emitting JSON, and the server validates again via `load_manifest`. Dual validation (client rejects out-of-range before sending; server rejects as IngestError) prevents round-trips and surfaces errors immediately.

[VERIFIED: bounds from apollo/synth/manifest.py constants (lines 67-77). ASSUMED: copy-and-maintain approach is acceptable for v1; a gen script is optional enhancement for future spec bumps.]

### Pattern 6: Drag-Drop Ingest Validation

**What:** Drop zone in the Corpus drill-in view accepts a directory drop or file selection. The pair files (call.mid + call_fm.json, and optionally response.mid) are uploaded via a multipart POST. The server runs full validation.

**Server-side validation pipeline** (D-13):

```python
@app.post("/ingest")
def ingest_pair():
    call_mid = request.files.get("call_mid")
    call_fm  = request.files.get("call_fm")
    response_mid = request.files.get("response_mid")  # optional at upload, required before training

    pair_path = allocate_next_nnn(pairs_root)

    # 1. Validate FM manifest (reuse shipped validator)
    fm_data = call_fm.read()
    try:
        json.loads(fm_data)  # pre-check JSON parse
        params = load_manifest_from_bytes(fm_data, str(pair_path))
    except IngestError as e:
        return jsonify({"ok": False, "error": str(e.reason)}), 400

    # 2. Validate MIDI via apollo.ingest.midi.load_notes
    try:
        notes = load_notes_from_bytes(call_mid.read(), str(pair_path))
    except IngestError as e:
        return jsonify({"ok": False, "error": str(e.reason)}), 400

    # 3. Write files + render call.wav (D-11/D-14)
    pair_path.mkdir(parents=True)
    (pair_path / "call_fm.json").write_bytes(fm_data)
    (pair_path / "call.mid").write_bytes(call_mid_bytes)
    audio = render(params, notes, pair_path=str(pair_path))  # in-process
    sf.write(str(pair_path / "call.wav"), audio, SR)

    if response_mid:
        (pair_path / "response.mid").write_bytes(response_mid.read())

    return jsonify({"ok": True, "nnn": pair_path.name})
```

Note: `load_manifest` in `manifest.py` takes a file path; a small wrapper that accepts bytes (write to a temp file, or extract the JSON-parse + validation logic) is needed. Alternatively, write the uploaded bytes to a NamedTemporaryFile, call `load_manifest(tmp.name, pair_path_str)` directly — this is the simplest approach.

[VERIFIED: load_manifest signature `(path: str, pair_path: str)` in manifest.py line 120. VERIFIED: render() signature `(params, notes, *, pair_path)` in render.py line 100. ASSUMED: NamedTemporaryFile approach for load_manifest will work cleanly in Flask request context.]

### Pattern 7: Loss-Over-Epochs Curve (native Canvas 2D)

**What:** A `<canvas>` element in the Training drill-in view. After each poll that returns new `loss_history` data, redraw the curve with `requestAnimationFrame`.

```javascript
function drawLossCurve(canvas, history) {
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  ctx.clearRect(0, 0, W, H);
  if (history.length < 2) return;

  const maxLoss = Math.max(...history.map(d => d.train_loss || 0));
  const minLoss = 0;
  const toX = i => (i / (history.length - 1)) * W;
  const toY = v => H - ((v - minLoss) / (maxLoss - minLoss || 1)) * H * 0.9;

  // train_loss (solid)
  ctx.beginPath();
  ctx.strokeStyle = '#6D28D9';  // --accent
  history.forEach((d, i) => {
    const x = toX(i), y = toY(d.train_loss);
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.stroke();

  // held_loss (dashed)
  ctx.beginPath();
  ctx.strokeStyle = '#15803D';  // success green
  ctx.setLineDash([4, 4]);
  history.filter(d => d.held_loss != null).forEach((d, i) => {
    const x = toX(history.indexOf(d)), y = toY(d.held_loss);
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.stroke();
  ctx.setLineDash([]);
}
```

[VERIFIED: train.py logs both train_loss and held_loss every `--log-every` epochs (default 10); `loss_history` list carries them. Canvas 2D API available in all modern browsers without deps.]

### Anti-Patterns to Avoid

- **Never bind to `0.0.0.0`** — always `127.0.0.1`. The app handles MIDI files and model weights; no network exposure.
- **Never subprocess render_call_wav** — it should be in-process. The DawDreamer warning suppression (`redirect_stderr`) already handles the benign output; subprocess adds complexity with no benefit.
- **Never trust browser-side manifest values without server re-validation** — the client editor can have bugs; `load_manifest` is the authoritative validator (D-13).
- **Never hardcode DawDreamer parameter indices** — always resolve from `get_parameters_description()`. See spike landmine above.
- **Never call `Flask.run(debug=True)` in production** — single-user local tool uses `debug=False` (verified in eval_grade.py).
- **Never use Tone.js FMSynth for this project** — it is 2-op only. If Tone.js is added in future, use only its `Oscillator` primitives, not `FMSynth`. [VERIFIED: Tone.js docs FMOscillator is a 2-op FM oscillator]
- **Never auto-retrain without debounce** — bulk drag-in of N pairs must trigger one train run (D-06). Use a server-side debounce timer (e.g., threading.Timer reset on each upload, fires after 2s of quiet).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| FM manifest validation | Custom JSON schema checker | `apollo.synth.manifest.load_manifest` | Existing, tested, raises IngestError with pair_path |
| MIDI file validation | Custom parser | `apollo.ingest.midi.load_notes` | Handles tempo/monophony/empty checks with correct error messages |
| call.wav rendering | Any custom DawDreamer wrapper | `apollo.synth.render.render_call_wav` | Single canonical render path (D-11); spike gotchas already handled |
| Pair discovery | Custom folder scanner | `apollo.ingest.pairs.discover_pairs` | Path-traversal guards already in place |
| Response MIDI generation | Any custom sampler | `apollo.scripts.generate` (subprocess) | Shipped, tested inference pipeline |
| Training execution | Any in-process training loop | `apollo.scripts.train` (subprocess) | D-02; the CLI handles all edge cases, checkpointing, logging |
| ADSR in Web Audio | Custom timing math from scratch | `AudioParam.linearRampToValueAtTime` + `setValueAtTime` | Standard Web Audio API; well-supported in all modern browsers |

**Key insight:** Phase 5's primary job is to glue shipped code together, not to build new ML or audio infrastructure. Every item in the "Don't Build" column is already tested and correct in the codebase.

---

## Common Pitfalls

### Pitfall 1: Blocking the Flask dev server during render_call_wav

**What goes wrong:** `render_call_wav` is called in the Flask request handler thread. While it runs (~0.1–0.2s for 1.5s audio at 44100 Hz), the browser hangs on the POST /ingest response.

**Why it happens:** Flask's development server is synchronous unless `threaded=True`. Even with threading, each request blocks its own thread.

**How to avoid:** Use `app.run(threaded=True)` so the training-status polling loop isn't blocked by a concurrent render. The render itself is fast enough that blocking the ingest request is acceptable — it is a user-facing action the user triggered intentionally.

**Warning signs:** 5+ second response times on ingest — indicates DawDreamer startup pathology, not normal render time.

### Pitfall 2: Training subprocess stdout deadlock

**What goes wrong:** `subprocess.Popen(stdout=PIPE)` with no reader causes the subprocess to block on a full pipe buffer (64 KB on macOS).

**Why it happens:** train.py emits stdout lines every `--log-every` epochs. For 300 epochs with `--log-every 10`, that's 30 lines — well under 64 KB. But stderr is also captured (stdout=PIPE, stderr=STDOUT funnels both); the DawDreamer benign warning is already suppressed inside render.py, so stderr from train.py is minimal.

**How to avoid:** The daemon thread reads `self._proc.stdout` line by line, which drains the pipe continuously. This is the standard pattern. DO NOT use `communicate()` — it blocks until subprocess exits, destroying the real-time progress effect.

**Warning signs:** Status endpoint always returns `status: running` with `epoch: 0` → stdout thread is not draining.

### Pitfall 3: Auto-retrain fires N times on bulk drag-in

**What goes wrong:** User drags 10 pairs at once. Each POST /ingest succeeds and triggers auto-retrain → 10 sequential training runs.

**Why it happens:** Naive auto-retrain trigger fires on every successful ingest.

**How to avoid:** Server-side debounce: `threading.Timer` that resets on each ingest and fires the training job after 2–3 s of quiet. Cancel the existing timer on each new ingest, create a new one.

**Warning signs:** Multiple training jobs queued in `TrainingJob.status` changes — detect by adding a `run_count` counter.

### Pitfall 4: Browser synth LFO phase mismatch vs server render

**What goes wrong:** The browser synth LFO sounds different from the server render because Web Audio `OscillatorNode` does not support phase reset (unlike Faust `os.osc` which resets per polyphonic voice).

**Why it happens:** Browser oscillators start from phase 0 at node creation, but at any given playback time their phase depends on wall clock, not note onset.

**How to avoid:** Create a new `OscillatorNode` for each note-on (don't reuse), starting it at the exact scheduled `when` time. This gives per-note phase reset that mirrors the Faust polyphonic voice behavior. [VERIFIED: Web Audio API best practice is to create new OscillatorNode per note and call osc.start(when) + osc.stop(when + duration)]

**Warning signs:** LFO seems out of phase with expected tremolo pattern on rapid successive notes — stale shared oscillator is being reused.

### Pitfall 5: call_fm.json path vs discovery_pairs call.wav requirement

**What goes wrong:** `apollo.ingest.pairs.discover_pairs` requires `call.wav` to exist (it checks for it). Phase 5's ingest flow creates pairs with `call.mid + call_fm.json` and then renders `call.wav` server-side. But if the render fails mid-way, the pair directory exists without `call.wav`, and subsequent `discover_pairs` calls will raise `IngestError("missing call.wav")`.

**Why it happens:** `discover_pairs` was designed for the fully-formed corpus; Phase 5 constructs pairs incrementally.

**How to avoid:** The app's own pair enumeration for the corpus list view should NOT use `discover_pairs` directly — it should scan for pairs by `(call.mid + call_fm.json)` presence rather than `call.wav`. Only the training CLI's `ingest` call needs `call.wav`. The app must render `call.wav` atomically as part of the ingest POST before acknowledging success.

**Warning signs:** Corpus tile shows pairs but training fails with IngestError missing call.wav.

### Pitfall 6: MIDI playback — response.mid must be parsed in browser

**What goes wrong:** The browser needs to play `response.mid` (and `call.mid`) through the Web Audio FM synth. MIDI files are binary; the browser cannot directly play them through the Web Audio FM graph without a MIDI parser.

**Why it happens:** `response.mid` is a standard MIDI file; `<audio>` element cannot play it through a custom Web Audio graph.

**How to avoid:** Include a lightweight vanilla JS MIDI file parser. Options:
- Hand-roll a minimal parser for Type-0/Type-1 MIDI (monophonic, known structure from Apollo corpus — 2–6 notes, no complex events).
- Use `jasmid` or `midi.js` vendored as a single file (MIT licensed).
- Expose a `/midi/nnn/call` endpoint that returns JSON `[{pitch, velocity, start, duration}]` from the server using `apollo.ingest.midi.load_notes` — the simplest approach for v1 (server does MIDI parsing, browser just schedules Web Audio notes).

**Recommended:** Server-side MIDI-to-JSON endpoint. The server can re-use `load_notes` to return note data; the browser schedules notes using the Web Audio synth. Avoids a JS MIDI parser entirely. [VERIFIED: load_notes returns list of Note(pitch, velocity, start, end); trivially serializable to JSON]

**Warning signs:** response.mid plays silently or as native MIDI (system synth) instead of through the FM synth.

---

## Code Examples

### MIDI-to-JSON Endpoint (server provides notes, browser plays them)

```python
# In apollo/app/app.py
from apollo.ingest.midi import load_notes

@app.get("/midi/<nnn>/<filename>")
def midi_notes(nnn, filename):
    # Validate nnn is a known pair to prevent path traversal
    pair_path = _validate_pair_nnn(nnn)  # raises 404 if unknown
    if filename not in ("call.mid", "response.mid"):
        abort(400)
    mid_path = pair_path / filename
    if not mid_path.is_file():
        abort(404)
    notes = load_notes(str(mid_path), str(pair_path), tempo_bpm=120.0)
    return jsonify([
        {"pitch": n.pitch, "velocity": n.velocity,
         "start": n.start, "duration": n.end - n.start}
        for n in notes
    ])
```

[VERIFIED: load_notes signature from apollo/ingest/midi.py. Note objects have pitch, velocity, start, end attributes confirmed by generate.py usage.]

### Status Endpoint + Frontend Poll

```python
# GET /status -> JSON
@app.get("/status")
def status():
    return jsonify(app.config["TRAINING_JOB"].snapshot())
```

```javascript
// Frontend polling loop in app.js
let pollInterval = null;

function startPolling() {
  if (pollInterval) return;
  pollInterval = setInterval(async () => {
    const data = await fetch('/status').then(r => r.json());
    updateTrainingUI(data);
    if (data.status === 'complete' || data.status === 'error') {
      clearInterval(pollInterval);
      pollInterval = null;
    }
  }, 1000);
}
```

### Debounced Auto-Retrain

```python
# In apollo/app/app.py
import threading

_debounce_timer = None
_DEBOUNCE_SECONDS = 3.0

def _debounced_retrain():
    """Fire training if auto-retrain enabled, after DEBOUNCE_SECONDS of quiet."""
    job = app.config["TRAINING_JOB"]
    job.start(
        pairs_root=app.config["PAIRS_ROOT"],
        epochs=300,
        output_dir="models"
    )

@app.post("/ingest")
def ingest_pair():
    # ... validation + write + render ...
    if app.config.get("AUTO_RETRAIN"):
        global _debounce_timer
        if _debounce_timer:
            _debounce_timer.cancel()
        _debounce_timer = threading.Timer(_DEBOUNCE_SECONDS, _debounced_retrain)
        _debounce_timer.daemon = True
        _debounce_timer.start()
    return jsonify({"ok": True, ...})
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual Ableton bounce for call.wav | Server-side render_call_wav from call_fm.json | Phase 6 (2026-06-02) | Phase 5 never needs to ask user to open Ableton |
| 4-op Operator-clone browser synth (UI-SPEC assumption) | 3-op v1.1 FM spec from spec.py | D-20 reconciliation (2026-06-02) | Synth is simpler; must mirror spec.py exactly |
| Static 1.0 FM patch | Optional LFO block (v1.1) in call_fm.json | Phase 7 (2026-06-02) | Browser synth must implement tremolo + vibrato LFO |
| generate.py required separate call.wav input | generate.py renders call.wav internally from call_fm.json | Phase 6 (06-03) | App only needs to provide call_mid + call_fm.json to inference |

**Deprecated/outdated:**
- SC#4 in ROADMAP.md "4 operators with selectable algorithms" — overridden by D-20: 3-op v1.1.
- SC#4/SC#7 "in-browser synth renders call.wav" — overridden by D-11/D-15: canonical render is server-side only.

---

## Proposed Requirement Breakdown (APP-01..APP-13)

The planner should formalize these as requirements. They cover the full Phase 5 surface area:

| Candidate ID | Description | Key Decisions |
|-------------|-------------|---------------|
| APP-01 | `apollo/app/` Flask app launches with `python -m apollo.app`, opens browser to 127.0.0.1, serves dashboard | D-01, D-04 |
| APP-02 | Dashboard shows 3 equal-weight tiles: Corpus (pair count + progress), Training (status + CTA), Generate (CTA + recent responses) | UI-SPEC Layout |
| APP-03 | Corpus drill-in: drag-drop MIDI + call_fm.json upload, validated server-side via apollo.ingest + load_manifest, written to data/pairs/NNN/ with rendered call.wav | D-09, D-13, D-14 |
| APP-04 | FM patch editor in Generate drill-in: exposes algorithm selector + per-operator ratio/level/ADSR sliders + optional LFO section; saves to call_fm.json | D-18, D-19, D-20 |
| APP-05 | Browser FM synth: 3-op v1.1 Web Audio graph, per-algorithm topology from spec.py, LFO tremolo/vibrato wired per CORPUS-CONVENTIONS.md formulas | D-15, D-16, D-19, D-20 |
| APP-06 | Patch editor live preview: changing any editor control immediately triggers browser synth playback of a short test note | D-16, D-18 |
| APP-07 | Training view: manual "Train model" button, auto-retrain-on-upload toggle with server-side debounce; POST /train subprocesses train.py | D-02, D-03, D-05, D-06 |
| APP-08 | Training view: live progress bar (epoch/total) + loss-over-epochs curve (canvas, train+held_loss), via 1s polling of GET /status | D-07, D-08 |
| APP-09 | Generate flow: user uploads call.mid, editor provides call_fm.json; POST /generate subprocesses generate.py; response.mid written to configurable store | D-02, D-12, D-17 |
| APP-10 | Response audition: server exposes GET /midi/<nnn>/<file> returning note JSON; browser plays call and response.mid through the same FM synth | D-16, D-17 |
| APP-11 | Corpus pair audition: per-pair call.mid auditionable in the corpus list view via same MIDI-to-JSON + browser synth | D-16 |
| APP-12 | Configurable response storage: in-app setting persists the response output directory; default data/responses/; listed and auditionable in-app | D-12 |
| APP-13 | Bundled FM presets: a set of starter call_fm.json presets (at least 3, covering different algorithms/timbres) available in the patch editor as starting points | D-18 |

---

## Open Questions (RESOLVED)

1. **MIDI upload for call.mid from browser**
   - What we know: The browser needs to upload a MIDI file for the call. HTML `<input type="file" accept=".mid">` works.
   - What's unclear: Whether the editor should also allow replacing `call.mid` after the patch is saved, or if it's one-shot per pair.
   - Recommendation: One-shot per pair for v1. The user uploads call.mid + submits the patch editor → pair is created. No mid-pair MIDI swap.
   - RESOLVED (Plan 04, Task 2): generate.html uses a one-shot `<input type="file" id="call-mid-input" accept=".mid">`; no mid-pair MIDI swap. (Corpus ingest upload is the analogous one-shot input in Plan 03, Task 2.)

2. **Checkpoint selection for generate**
   - What we know: `generate.py` requires a checkpoint path. Multiple checkpoints accumulate in `models/` over training iterations.
   - What's unclear: Should the app always use the most recent checkpoint, or let the user pick?
   - Recommendation: Always use the most recent checkpoint (sorted by mtime or embedded timestamp). "Use latest" is the correct UX for a demo app. Expose the checkpoint path in the UI for transparency but don't require the user to choose.
   - RESOLVED (Plan 04, Task 2): `_latest_checkpoint()` globs `models/*.pt` and returns max by `st_mtime`; the chosen path is surfaced in the /generate JSON (`"checkpoint"`) for UI transparency.

3. **Response.mid storage path vs. data/pairs/NNN/**
   - What we know: generate.py writes `response_NNN.mid` alongside `call.mid` in the pair directory (D-17 of generate.py). D-12 says responses go to a configurable location.
   - What's unclear: D-12 and generate.py's behavior conflict — generate.py writes to the pair dir, not a separate responses dir.
   - Recommendation: Pass `--output-dir` (or accept the pair dir default from generate.py) and then copy/move the result to the configurable responses dir. Or: don't use generate.py's default path — instead pass the response output path explicitly. Check generate.py's actual arg surface at plan time.
   - RESOLVED (Plan 04, Task 2): generate.py has NO `--output-dir`; it writes `response_NNN.mid` into the pair dir. The /generate route copies the newest `response_*.mid` into `RESPONSES_DIR` (D-12 configurable store) after the subprocess returns.

4. **Pair directory allocates NNN — race condition on concurrent uploads?**
   - What we know: Pairs are `data/pairs/NNN/` with sequential NNN. The app must allocate the next NNN.
   - What's unclear: If two browser tabs upload simultaneously, they could race on the same NNN.
   - Recommendation: Hold a threading.Lock around "find max NNN + mkdir(NNN+1)". Single-user local app makes this unlikely, but the lock costs nothing.
   - RESOLVED (Plan 03, Task 1): `_allocate_next_nnn()` holds `_alloc_lock` around find-max-NNN + `mkdir`, eliminating the concurrent-upload race.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11 | All server code | ✓ | 3.11 (project venv) | — |
| Flask | APP-01..APP-13 | ✓ | Already installed (eval/web) | — |
| DawDreamer | D-11 render_call_wav | ✓ | 0.8.3 (confirmed 06-01) | — |
| apollo.synth | APP-03..APP-09 | ✓ | Shipped Phase 6/7 | — |
| apollo.ingest | APP-03 | ✓ | Shipped Phase 1 | — |
| Web Audio API | APP-05..APP-11 | ✓ | Native browser (Chrome/Safari/Firefox) | — |
| soundfile (sf) | render_call_wav writes WAV | ✓ | Already in project venv | — |

No missing dependencies. All required libraries are already in the project venv (confirmed by 06-01 decision in STATE.md and Phase 6 execution). [VERIFIED: STATE.md "06-01: A4 CLEARED — dawdreamer==0.8.3 + torch 2.12.0 import cleanly in one .venv"]

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Audition-quality ADSR via linearRampToValueAtTime is "close enough" to Faust en.adsr() for preview | Pattern 4 ADSR mapping | Browser synth sounds noticeably different from server render; degrades demo value but does not break correctness (D-15 explicitly allows this) |
| A2 | Linear approximation for vibrato LFO (instead of exact pow(2, ...)) is acceptable for audition | Pattern 4 LFO mapping | Vibrato pitch deviation slightly off at high depth values; at depth=1 error < 0.1% at 50-cent range |
| A3 | Copy-and-maintain spec constants JS file is acceptable for v1 (no gen script) | Pattern 5 | If spec.py is bumped without updating spec_constants.js, editor emits manifests that pass client validation but fail server validation; catches at server boundary |
| A4 | Single-user, no concurrent training runs — threading.Lock + timer is sufficient | Pattern 2, Pattern 6 | Two browser tabs could start two training jobs; second would silently fail (D-03 background job concept does not require queuing) |
| A5 | DawDreamer import in Flask request context does not introduce global state issues | Pattern 3 | DawDreamer uses JUCE internally; multiple sequential render calls in the same process should be safe given existing usage in scripts/render_corpus.py |

---

## Sources

### Primary (HIGH confidence)
- `apollo/synth/spec.py` — FM spec, algorithm topologies, LFO formulas (VERIFIED directly)
- `apollo/synth/manifest.py` — Validation bounds, load_manifest signature (VERIFIED directly)
- `apollo/synth/render.py` — render_call_wav, render, DawDreamer gotchas (VERIFIED directly)
- `data/pairs/CORPUS-CONVENTIONS.md` — LFO tremolo/vibrato parity formulas (VERIFIED directly)
- `apollo/eval/web/app.py` + `apollo/scripts/eval_grade.py` — Flask pattern, 127.0.0.1 binding, launch (VERIFIED directly)
- `apollo/scripts/train.py` — stdout format "epoch E/N train_loss=X held_loss=Y" (VERIFIED directly line 174)
- `apollo/scripts/generate.py` — CLI surface, pair dir assumptions (VERIFIED directly)
- `.claude/skills/spike-findings-apollo/references/synth-independent-rendering.md` — DawDreamer landmines (VERIFIED directly)
- MDN Web Docs: `OscillatorNode.frequency` (AudioParam a-rate, summable via connect) (VERIFIED via WebFetch)

### Secondary (MEDIUM confidence)
- greweb.me FM with Web Audio API tutorial — graph topology for carrier/modulator (VERIFIED via WebFetch)
- MDN AudioParam `linearRampToValueAtTime` + `setValueAtTime` — ADSR scheduling patterns (WebSearch verified)

### Tertiary (LOW confidence)
- Tone.js FMOscillator docs — confirmed 2-op limitation (WebSearch; confirms UI-SPEC note)

---

## Metadata

**Confidence breakdown:**
- Flask app structure: HIGH — exact pattern confirmed in shipped apollo/eval/web/
- Web Audio FM graph: HIGH — OscillatorNode.frequency as AudioParam confirmed; modulator connect() semantics confirmed
- LFO Web Audio implementation: MEDIUM — tremolo formula verified; vibrato linear approximation is stated assumption (A2)
- Schema lockstep: HIGH — bounds verified directly from manifest.py
- Background training job: HIGH — train.py stdout format verified; threading+Popen pattern is standard
- Pitfalls: HIGH — derived from reading actual shipped code, not from general web knowledge

**Research date:** 2026-06-02
**Valid until:** 2026-07-02 (stable APIs; FM spec is frozen; Flask/Web Audio stable)

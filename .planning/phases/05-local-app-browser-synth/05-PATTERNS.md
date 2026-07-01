# Phase 5: Local App & In-Browser Synth — Pattern Map

**Mapped:** 2026-06-02
**Files analyzed:** 13 new/modified files
**Analogs found:** 12 / 13

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `apollo/app/__init__.py` | config | — | `apollo/eval/web/__init__.py` (implied empty) | exact |
| `apollo/app/__main__.py` | utility (launcher) | request-response | `apollo/scripts/eval_grade.py` | exact |
| `apollo/app/app.py` | controller (Flask factory) | request-response + CRUD | `apollo/eval/web/app.py` | exact |
| `apollo/app/jobs.py` | service | event-driven (subprocess + threading) | no analog (new pattern) | none |
| `apollo/app/static/style.css` | config (CSS) | — | `apollo/eval/web/static/style.css` | exact (extend) |
| `apollo/app/static/app.js` | utility (frontend) | request-response + polling | `apollo/eval/web/static/grade.js` | role-match |
| `apollo/app/static/synth.js` | utility (Web Audio engine) | event-driven | no analog | none |
| `apollo/app/static/spec_constants.js` | config (JS constants) | — | `apollo/synth/spec.py` + `apollo/synth/manifest.py` | derived |
| `apollo/app/templates/base.html` | component (template) | — | `apollo/eval/web/templates/index.html` | role-match |
| `apollo/app/templates/dashboard.html` | component (template) | — | `apollo/eval/web/templates/index.html` | role-match |
| `apollo/app/templates/corpus.html` | component (template) | CRUD | `apollo/eval/web/templates/pair.html` | role-match |
| `apollo/app/templates/training.html` | component (template) | streaming | `apollo/eval/web/templates/pair.html` | role-match |
| `apollo/app/templates/generate.html` | component (template) | request-response | `apollo/eval/web/templates/pair.html` | role-match |

---

## Pattern Assignments

### `apollo/app/__main__.py` (utility, launcher)

**Analog:** `apollo/scripts/eval_grade.py`

**Launch pattern** (lines 33-56 of eval_grade.py):
```python
# eval_grade.py: single-command launch, 127.0.0.1, debug=False
app = create_app(...)
app.run(host="127.0.0.1", port=args.port, debug=False)
```

**__main__.py must add `webbrowser.open` + `threaded=True`** (RESEARCH Pattern 1):
```python
# apollo/app/__main__.py — mirrors eval_grade.py but opens browser automatically
import argparse, sys, webbrowser, threading
from apollo.app.app import create_app

def main(argv=None):
    parser = argparse.ArgumentParser(description="Launch Apollo local app.")
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--pairs-root", default="data/pairs")
    args = parser.parse_args(argv)

    app = create_app(pairs_root=args.pairs_root)
    url = f"http://127.0.0.1:{args.port}/"
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    print(f"Apollo app: {url}", file=sys.stderr)
    # threaded=True: polling /status during training is concurrent with the training thread
    app.run(host="127.0.0.1", port=args.port, debug=False, threaded=True)
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

**Key delta from eval_grade.py:** add `webbrowser.open`, `threading.Timer(0.5, ...)`, `threaded=True`. Never `debug=True`. Never bind to `0.0.0.0`.

---

### `apollo/app/app.py` (controller, request-response + CRUD)

**Analog:** `apollo/eval/web/app.py` (full file, 217 lines)

**create_app factory pattern** (lines 88-104 of eval/web/app.py):
```python
def create_app(
    pairs_root: str,
    run_id: str,
    ...
) -> Flask:
    app = Flask(__name__)
    # Resolve to absolute path — Flask send_file resolves relative against
    # app's root_path (apollo/eval/web/), NOT cwd.
    app.config["PAIRS_ROOT"] = Path(pairs_root).resolve()
    app.config["RUN_ID"] = run_id
    ...
    return app
```

**_validate_nnn guard pattern** (lines 108-110 of eval/web/app.py):
```python
def _validate_nnn(nnn: str) -> None:
    if nnn not in _heldout_set():
        abort(404)
```
Phase 5 equivalent: `_validate_nnn` checks against `_known_pairs_set()` from the filesystem, not `enumerate_heldout`. Same abort(404) pattern.

**send_file audio route pattern** (lines 144-150 of eval/web/app.py):
```python
@app.get("/audio/<nnn>/call.wav")
def call_audio(nnn):
    _validate_nnn(nnn)
    path = app.config["PAIRS_ROOT"] / nnn / "call.wav"
    if not path.is_file():
        abort(404)
    return send_file(path, mimetype="audio/wav")
```

**POST handler with JSON response pattern** (lines 162-188 of eval/web/app.py):
```python
@app.post("/score")
def submit_score():
    data = request.get_json(silent=True) or {}
    try:
        pair_id = str(data["pair_id"])
        ...
    except (KeyError, TypeError, ValueError):
        return jsonify({"ok": False, "error": "bad payload"}), 400
    ...
    return jsonify({"ok": True, "next": next_nnn})
```
Phase 5 `/ingest`, `/train`, `/generate` all follow this same `request.get_json → validate → return jsonify({"ok": True/False, ...})` shape.

**Phase 5 additions vs. eval/web/app.py** (from RESEARCH Pattern 6 + Code Examples):
```python
# Routes that have no eval analog — paste directly from RESEARCH.md
from apollo.ingest.midi import load_notes
from apollo.synth.manifest import load_manifest
from apollo.synth.render import render_call_wav

@app.get("/midi/<nnn>/<filename>")
def midi_notes(nnn, filename):
    pair_path = _validate_pair_nnn(nnn)   # raises 404 if unknown
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

@app.get("/status")
def status():
    return jsonify(app.config["TRAINING_JOB"].snapshot())
```

**Critical import list for app.py** (inferred from all analogs):
```python
from __future__ import annotations
import json, threading
from pathlib import Path
from flask import Flask, abort, jsonify, render_template, request, send_file
from apollo.ingest.errors import IngestError
from apollo.ingest.midi import load_notes
from apollo.synth.manifest import load_manifest
from apollo.synth.render import render_call_wav
from apollo.app.jobs import TrainingJob
```

---

### `apollo/app/jobs.py` (service, event-driven — no analog)

No existing analog. Use RESEARCH Pattern 2 verbatim:

```python
# apollo/app/jobs.py — full class from RESEARCH.md Pattern 2
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
            ...
        cmd = [
            "python", "-m", "apollo.scripts.train",
            pairs_root,
            "--epochs", str(epochs),
            "--output-dir", output_dir,
        ]
        self._proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1   # line-buffered to avoid deadlock
        )
        t = threading.Thread(target=self._read_stdout, daemon=True)
        t.start()
        return True

    def _read_stdout(self):
        # train.py stdout format VERIFIED at apollo/scripts/train.py line 174:
        # "epoch {E}/{N}  train_loss={X:.4f}  held_loss={Y:.4f}"
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
                    self.loss_history.append({...})
        ret = self._proc.wait()
        with self._lock:
            self.status = "complete" if ret == 0 else "error"

    def snapshot(self) -> dict:
        with self._lock:
            return {"status": self.status, "epoch": self.epoch, ...}
```

**Critical:** DO NOT use `communicate()` (blocks until exit, destroys real-time progress). DO use `bufsize=1, text=True` + line iteration.

---

### `apollo/app/static/style.css` (config, CSS extension)

**Analog:** `apollo/eval/web/static/style.css` (full file, 50 lines)

**Token system to extend** (lines 1-11 of eval/web/static/style.css):
```css
:root {
  --bg: #FAFAFA;
  --text: #1A1A1A;
  --surface: #F0F0F0;
  --muted: #666666;
  --accent: #0066CC;      /* OVERRIDE to #6D28D9 for Phase 5 (UI-SPEC) */
  --destructive: #CC3333;
  --xs: 4px;  --sm: 8px;  --md: 16px;  --lg: 24px;  --xl: 32px;
  --font-body: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  --font-mono: ui-monospace, SFMono-Regular, Menlo, monospace;
}
```

**Component classes to reuse verbatim** (lines 19-49 of eval/web/static/style.css):
`.glyph`, `.action`, `.primary`, `.primary[disabled]`, `.secondary`, `.muted`, `.hidden`, `.error`, `.segmented`, `.score-btn`, `.score-btn.selected`, `.mono`, `.progress`

**Phase 5 additions** (from UI-SPEC):
```css
/* Phase 5 overrides eval/web tokens */
:root {
  --accent: #6D28D9;        /* UI-SPEC override: purple instead of blue */
  --2xl: 48px;              /* new spacing tokens */
  --3xl: 64px;
}
/* New layout rules */
.tile-grid { display: flex; gap: var(--xl); }
.tile { flex: 1; background: var(--surface); padding: var(--lg); }
.display { font-size: 40px; font-weight: 700; font-family: var(--font-mono); }
.heading { font-size: 24px; font-weight: 700; }
.trust-badge { font-size: 14px; color: var(--muted); }
.trust-badge .glyph.accent { color: var(--accent); }
/* Progress bar */
.progress-bar { height: 6px; background: var(--surface); }
.progress-bar-fill { height: 100%; background: var(--accent); }
/* Patch editor */
.op-panel { background: var(--surface); padding: var(--md); margin-bottom: var(--sm); }
.lfo-section details summary { cursor: pointer; }
/* Canvas chart container */
.loss-chart-wrap { position: relative; width: 100%; }
.loss-chart-wrap canvas { display: block; width: 100%; }
```

---

### `apollo/app/static/app.js` (utility, polling + UI state)

**Analog:** `apollo/eval/web/static/grade.js` (full file, 140 lines)

**IIFE + data-attribute pattern** (lines 1-16 of grade.js):
```javascript
(function () {
  const nnn = document.body.dataset.nnn;
  if (!nnn) return;
  // All state in one object
  const state = { fit: null, coherence: null, playing: false };
  ...
})();
```
Phase 5 app.js wraps each view's logic in an IIFE. State lives in one `const state = {}` object per view.

**Fetch + JSON error handling pattern** (lines 59-87 of grade.js):
```javascript
async function submit() {
  try {
    const r = await fetch('/score', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await r.json();
    if (!r.ok || !data.ok) {
      showError("...");
      return;
    }
    ...
  } catch (e) {
    showError("Network error. Score not saved.");
  }
}
```

**Error display pattern** (lines 87-95 of grade.js):
```javascript
function showError(msg) {
  let el = document.querySelector('.error');
  if (!el) {
    el = document.createElement('div');
    el.className = 'error';
    submitBtn.parentNode.appendChild(el);
  }
  el.textContent = msg;
}
```

**Polling loop pattern** (from RESEARCH Pattern 7 / Code Examples):
```javascript
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
  }, 1000);   // ~1s (D-07)
}
```

**Canvas loss curve draw pattern** (from RESEARCH Pattern 7):
```javascript
function drawLossCurve(canvas, history) {
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  ctx.clearRect(0, 0, W, H);
  if (history.length < 2) return;
  const maxLoss = Math.max(...history.map(d => d.train_loss || 0));
  const toX = i => (i / (history.length - 1)) * W;
  const toY = v => H - ((v / (maxLoss || 1))) * H * 0.9;
  ctx.beginPath();
  ctx.strokeStyle = '#6D28D9';   // --accent
  history.forEach((d, i) => {
    const x = toX(i), y = toY(d.train_loss);
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.stroke();
  ctx.beginPath();
  ctx.strokeStyle = '#15803D';   // success green
  ctx.setLineDash([4, 4]);
  history.filter(d => d.held_loss != null).forEach((d, i) => { ... });
  ctx.stroke();
  ctx.setLineDash([]);
}
```

---

### `apollo/app/static/synth.js` (utility, Web Audio engine — no analog)

No existing analog. Use RESEARCH Patterns 4 verbatim. Key excerpts:

**Note scheduling entry point** (RESEARCH Pattern 4):
```javascript
function playNote(audioCtx, patch, pitch, velocity, when, duration) {
  const freq = midiToHz(pitch);   // 440 * 2^((pitch-69)/12)
  // Build per-algorithm carrier/modulator Web Audio graph
  // per-operator: OscillatorNode + GainNode(ADSR)
  // modulation: scaled GainNode(op.level * freq) connected to carrier.osc.frequency
  // LFO: separate OscillatorNode per note (new node per note-on = phase reset)
}
```

**ADSR scheduling** (RESEARCH Pattern 4):
```javascript
function applyAdsr(gainParam, op, when, noteDuration) {
  gainParam.cancelScheduledValues(when);
  gainParam.setValueAtTime(0, when);
  gainParam.linearRampToValueAtTime(1.0, when + op.attack);
  gainParam.linearRampToValueAtTime(op.sustain, when + op.attack + op.decay);
  gainParam.setValueAtTime(op.sustain, when + noteDuration);
  gainParam.linearRampToValueAtTime(0, when + noteDuration + op.release);
}
```

**LFO attachment** (RESEARCH Pattern 4, formulas from CORPUS-CONVENTIONS.md):
```javascript
function attachLfo(audioCtx, patch, carriers, freq, when) {
  if (!patch.lfo) return;
  // lfo_wave: 0=sine, 1=triangle, 2=square — mirrors LfoWave IntEnum
  // TREMOLO (target=0): lvl_mod = 1 - depth*(1-lfo_uni)
  // VIBRATO (target=1): linear approx of pow(2, lfo_bi*depth*50/1200)
}
```

**Algorithm topology mapping** (from spec.py `_body_no_lfo` lines 259-282):
- STACK (0): op3 → op2 → op1 (carrier). `mod = env * level * freq` connected to next osc.frequency
- PARALLEL_MODS (1): op2 and op3 both → op1
- CARRIER_PAIR (2): op3 → op1; op2 is an independent additive carrier

---

### `apollo/app/static/spec_constants.js` (config, JS constants derived from spec.py)

**Source analog:** `apollo/synth/spec.py` (lines 46-153) + `apollo/synth/manifest.py` (lines 57-88)

**Values to copy verbatim** (from manifest.py lines 57-88):
```javascript
// spec_constants.js — derived from apollo/synth/spec.py + manifest.py
// Do NOT edit manually — update spec.py first, then re-derive.
const SPEC_VERSION = "1.1";
const N_OPERATORS = 3;
const ALGORITHMS = {STACK: 0, PARALLEL_MODS: 1, CARRIER_PAIR: 2};
const BOUNDS = {
  ratio:     [0.5, 12.0],   // manifest.py RATIO_MIN/MAX
  level:     [0.0,  1.0],   // LEVEL_MIN/MAX
  attack:    [0.0,  2.0],   // ADSR_MIN/MAX
  decay:     [0.0,  2.0],
  sustain:   [0.0,  1.0],   // SUSTAIN_MIN/MAX
  release:   [0.0,  2.0],
  gain:      [0.0,  1.0],   // GAIN_MIN/MAX
  lfo_rate:  [0.05, 20.0],  // LFO_RATE_MIN/MAX
  lfo_depth: [0.0,  1.0],   // LFO_DEPTH_MIN/MAX
  lfo_wave:  {valid: [0, 1, 2]},   // LfoWave: SINE=0, TRIANGLE=1, SQUARE=2
  lfo_target:{valid: [0, 1]},      // LfoTarget: LEVEL=0, PITCH=1
};
const LFO_WAVES   = {SINE: 0, TRIANGLE: 1, SQUARE: 2};
const LFO_TARGETS = {LEVEL: 0, PITCH: 1};
```

**Client-side validation must mirror `manifest.py._check_number`** (lines 91-103 of manifest.py):
```javascript
function checkBounds(value, field) {
  const [lo, hi] = BOUNDS[field];
  if (typeof value !== 'number' || !isFinite(value)) return false;
  return value >= lo && value <= hi;
}
```

---

### `apollo/app/templates/base.html` (component, shared layout)

**Analog:** `apollo/eval/web/templates/index.html` (lines 1-8: head block)

```html
<!-- base.html: extends eval/web template head pattern -->
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Apollo · {% block title %}{% endblock %}</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
  <!-- Trust badge: persistent, quiet (UI-SPEC) -->
  <header>
    <span class="trust-badge">
      <span class="glyph accent">◉</span>
      Runs on your machine — nothing is uploaded
    </span>
    <nav>...</nav>
  </header>
  <main class="column">{% block content %}{% endblock %}</main>
  <script src="{{ url_for('static', filename='app.js') }}"></script>
</body>
</html>
```

**Key pattern:** `url_for('static', filename='...')` for all asset refs (eval/web pattern, lines 6 and 72 of pair.html).

---

### `apollo/app/templates/dashboard.html` (component, 3-tile home)

**Analog:** `apollo/eval/web/templates/index.html`

**Progress display pattern** (lines 11-12 of index.html):
```html
<p class="progress">{{ n_graded }} / {{ n_total }} pairs scored — {{ n_remaining }} remaining</p>
```
Phase 5 equivalent: `{{ n_pairs }} of 30 pairs — keep going` (UI-SPEC copy, Display size = `class="display"`).

**Conditional empty state pattern** (lines 13-22 of index.html):
```html
{% if n_total == 0 %}
  <section class="empty">
    <h2>No held-out pairs found.</h2>
    ...
  </section>
{% elif n_remaining == 0 %}
  <p class="done-banner">...</p>
{% endif %}
```
Phase 5: same `{% if n_pairs == 0 %}` guard with UI-SPEC empty state copy.

---

### `apollo/app/templates/corpus.html` (component, CRUD)

**Analog:** `apollo/eval/web/templates/index.html` (worklist pattern) + `pair.html` (audio pattern)

**Worklist item pattern** (lines 23-46 of index.html):
```html
<ul class="worklist">
  {% for nnn in pairs %}
    <li class="row ...">
      <span class="glyph accent">✓</span>
      <span class="pair-id">{{ nnn }}</span>
      <a class="action secondary" href="...">Re-score</a>
    </li>
  {% endfor %}
</ul>
```

**Inline validation error pattern** (from `.error` CSS class in style.css line 49):
```html
<div class="error">{{ error_message }}</div>
```

---

### `apollo/app/templates/training.html` (component, streaming)

**Analog:** `apollo/eval/web/templates/pair.html`

**Button + disabled state pattern** (line 51 of pair.html):
```html
<button id="submit" class="primary" disabled>Submit & next →</button>
<span id="submit-hint" class="muted hidden">Set both scores to enable submit.</span>
```
Phase 5: `<button id="train-btn" class="primary">Train model</button>` with status-driven disabled state.

**Hidden/reveal pattern** (line 56 of pair.html):
```html
<aside id="reveal-aside" class="hidden mono"></aside>
```
Phase 5: `<div id="training-progress" class="hidden">` shown when training starts.

**Canvas placeholder:**
```html
<canvas id="loss-chart" width="600" height="200"></canvas>
```

---

### `apollo/app/templates/generate.html` (component, request-response)

**Analog:** `apollo/eval/web/templates/pair.html`

**Audio control pattern** (lines 12-19 of pair.html):
```html
<section class="audio-block">
  <label>Call</label>
  <audio id="audio-call" controls ...></audio>
  <label>Response</label>
  <audio id="audio-response" controls ...></audio>
  <button id="play-sequence" class="primary">▶ Play call → response</button>
</section>
```
Phase 5: Replace `<audio>` element with `<button id="play-call">` + Web Audio FM synth playback (D-15/D-16 — no `<audio>` for MIDI).

---

## Shared Patterns

### 127.0.0.1 Binding (non-negotiable)
**Source:** `apollo/scripts/eval_grade.py` line 55
**Apply to:** `apollo/app/__main__.py`
```python
app.run(host="127.0.0.1", port=args.port, debug=False)
```
Phase 5 adds `threaded=True` because training poll `/status` must be served concurrently.

### Flask create_app Factory
**Source:** `apollo/eval/web/app.py` lines 88-104
**Apply to:** `apollo/app/app.py`
```python
def create_app(pairs_root: str, ...) -> Flask:
    app = Flask(__name__)
    app.config["PAIRS_ROOT"] = Path(pairs_root).resolve()  # always resolve to abs
    ...
    return app
```
Always resolve `pairs_root` to an absolute path — `send_file` resolves relative against app's `root_path`, not `cwd`.

### NNN Path-Traversal Guard
**Source:** `apollo/eval/web/app.py` lines 108-110 + `apollo/ingest/pairs.py` lines 69-75
**Apply to:** All routes with `<nnn>` in `apollo/app/app.py`
```python
def _validate_nnn(nnn: str) -> None:
    if nnn not in _known_pairs_set():
        abort(404)
```
For Phase 5, `_known_pairs_set()` scans `data/pairs/NNN/` for dirs that contain `call.mid + call_fm.json` (not `discover_pairs` — see Pitfall 5 in RESEARCH).

### IngestError → HTTP 400
**Source:** `apollo/eval/web/app.py` lines 162-178 (pattern); `apollo/ingest/errors.py` lines 15-21
**Apply to:** `apollo/app/app.py` POST `/ingest`
```python
from apollo.ingest.errors import IngestError
try:
    params = load_manifest(tmp.name, str(pair_path))
except IngestError as e:
    return jsonify({"ok": False, "error": str(e.reason)}), 400
```
Always catch `IngestError` and return `{"ok": False, "error": e.reason}` — expose `reason`, not the full exception.

### JSON Response Shape
**Source:** `apollo/eval/web/app.py` lines 188, 198, 213
**Apply to:** All JSON endpoints in `apollo/app/app.py`
```python
return jsonify({"ok": True, ...})       # success
return jsonify({"ok": False, "error": "..."}), 400  # failure
```

### Jinja2 Template Structure
**Source:** `apollo/eval/web/templates/index.html` lines 1-8; `pair.html` lines 1-9
**Apply to:** All `apollo/app/templates/*.html`
```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Apollo · ...</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body data-nnn="{{ nnn }}">   <!-- data attributes carry state to JS -->
```
Always use `url_for('static', filename='...')`. JS reads page state from `document.body.dataset.*`.

### JS Fetch + Error Display
**Source:** `apollo/eval/web/static/grade.js` lines 59-95
**Apply to:** All fetch calls in `apollo/app/static/app.js`
```javascript
try {
  const r = await fetch(url, {method, headers, body});
  const data = await r.json();
  if (!r.ok || !data.ok) { showError(data.error || "Server error."); return; }
  // success path
} catch (e) {
  showError("Network error.");
}
```

### CSS Token Inheritance
**Source:** `apollo/eval/web/static/style.css` lines 1-11
**Apply to:** `apollo/app/static/style.css`
Copy the full token block, then override `--accent: #6D28D9` and add `--2xl`/`--3xl`. Do NOT rename existing tokens — eval/web templates may be loaded in the same session.

---

## Ingest Module Reuse Patterns

### `apollo/ingest/midi.load_notes` (for `/midi/<nnn>/<file>` endpoint)
**Source:** `apollo/ingest/midi.py` lines 44-60
```python
# Signature:
def load_notes(mid_path: str, pair_path: str, tempo_bpm: float = 120.0) -> List[Note]:
# Returns Note(pitch, velocity, start, end) — start/end in seconds
# Raises IngestError on: parse failure, != 1 track, 0 notes, > MAX_NOTES_PER_PAIR, overlap
```

### `apollo/synth/manifest.load_manifest` (for `/ingest` validation)
**Source:** `apollo/synth/manifest.py` lines 120-193
```python
# Signature:
def load_manifest(path: str, pair_path: str) -> FmParams:
# Takes a FILE PATH — write upload bytes to NamedTemporaryFile first
# Raises IngestError with e.reason string
```

### `apollo/synth/render.render_call_wav` (for `/ingest` canonical render)
**Source:** `apollo/synth/render.py` lines 200-222
```python
# Signature:
def render_call_wav(manifest_path: str, mid_path: str, *, pair_path: str,
                    call_bpm: float = 120.0, notes=None) -> np.ndarray:
# Returns normalized float32 mono array; caller writes to WAV with soundfile
# ALWAYS call in-process (never subprocess) — RESEARCH Pattern 3
```

### `apollo/ingest/pairs.discover_pairs` (NOT used for app's pair list)
**Source:** `apollo/ingest/pairs.py` lines 41-99
**Warning:** `discover_pairs` requires `call.wav` to exist. Phase 5 app's own corpus list must scan for `call.mid + call_fm.json` presence instead (RESEARCH Pitfall 5). Only the training CLI uses `discover_pairs`.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `apollo/app/jobs.py` | service | event-driven | No background subprocess + threading job pattern exists in codebase |
| `apollo/app/static/synth.js` | utility | event-driven | No Web Audio code in codebase; first JS audio implementation |

Both must be hand-rolled from RESEARCH.md Patterns 2 and 4 respectively.

---

## Metadata

**Analog search scope:** `apollo/eval/web/`, `apollo/scripts/`, `apollo/ingest/`, `apollo/synth/`
**Files read:** 14
**Pattern extraction date:** 2026-06-02

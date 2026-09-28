// Apollo TimeScale — Max for Live MIDI Effect.
//
// One knob (-50%..+50%) that tightens or loosens the *instrument's* time-based
// parameters on this track, written as clip automation over the selected range
// of the selected MIDI clip. Outside that range nothing changes: at the end of
// the range every parameter is back at whatever it was before. MIDI notes are
// never touched.
//
//   knob p (%)  ->  time factor k = 2^(p/50)   (-50% = x0.5, 0% = x1, +50% = x2)
//
//   durations (ms/s)      x k      attack, decay, release, hold, delay, glide...
//   LFO rates (Hz)        / k      a longer shape needs a slower LFO
//   Operator "Time" (%)   + p      Operator's own global envelope-time knob
//
// Selected range = span of the selected notes in the clip, or the whole clip
// (its loop region if looping) when no notes are selected.
//
// Classic Max `js` is ES5 — keep this file ES5. The pure helpers at the top are
// also exported for Node so they can be unit-tested outside Live.

// ---------------------------------------------------------------------------
// Pure helpers (no Max / LiveAPI dependencies)
// ---------------------------------------------------------------------------

var P_MIN = -50;
var P_MAX = 50;
var GRID = 0.25; // beats (1/16 note) — resolution when re-scaling existing automation

function clampPercent(p) {
  p = Number(p);
  if (isNaN(p)) return 0;
  return Math.max(P_MIN, Math.min(P_MAX, p));
}

// -50% -> 0.5, 0% -> 1, +50% -> 2. Exponential so equal knob moves feel equal.
function percentToFactor(p) {
  return Math.pow(2, clampPercent(p) / 50);
}

// Parameter names that denote a duration.
var TIME_NAME_RE = /(attack|decay|release|hold|delay|fade ?in|fade ?out|glide|portamento|slide time|\btime\b|\batt\b|\bdec\b|\brel\b)/i;
// Parameter names that denote an LFO / modulator speed.
var RATE_NAME_RE = /(rate|speed|lfo.*freq)/i;
// Things that match the above but are not what we want (modulation depths,
// shapes, switches, levels).
var EXCLUDE_RE = /(<|slope|shape|mode|sync|level|sustain|amount|\bamt\b|feedback|mix|loop|retrig|legato|vel|key)/i;

// "time" | "rate" | null
function classifyParamName(name) {
  name = String(name || "");
  if (EXCLUDE_RE.test(name)) return null;
  if (RATE_NAME_RE.test(name)) return "rate";
  if (TIME_NAME_RE.test(name)) return "time";
  return null;
}

// Parse a Live display string into { value, unit } with unit "ms", "hz" or "%".
// "12.3 ms" -> 12.3 ms, "1.20 s" -> 1200 ms, "2.5 Hz", "1.2 kHz" -> 1200 hz,
// "-35 %" -> -35 %. null if unparseable (e.g. synced rates like "1/4").
function parseDisplay(str) {
  var m = /(-?\d+(?:\.\d+)?)\s*(ms|s|khz|hz|%)(?![a-z])/i.exec(String(str || ""));
  if (!m) return null;
  var v = parseFloat(m[1]);
  var u = m[2].toLowerCase();
  if (u === "s") return { value: v * 1000, unit: "ms" };
  if (u === "khz") return { value: v * 1000, unit: "hz" };
  return { value: v, unit: u };
}

// Find the raw parameter value whose *displayed* value is closest to `target`.
// `display(raw)` returns a number or null. Assumes display is monotonic over
// [min, max]; works rising or falling. Returns a raw value inside [min, max].
function solveForDisplay(display, min, max, target, iterations) {
  iterations = iterations || 24;
  var dMin = display(min);
  var dMax = display(max);
  if (dMin === null || dMax === null) return null;
  var rising = dMax >= dMin;
  var lo = min, hi = max;
  if (rising ? target <= dMin : target >= dMin) return min;
  if (rising ? target >= dMax : target <= dMax) return max;
  for (var i = 0; i < iterations; i++) {
    var mid = (lo + hi) / 2;
    var d = display(mid);
    if (d === null) return null;
    if ((d < target) === rising) lo = mid; else hi = mid;
  }
  return (lo + hi) / 2;
}

// Scaled display value for a param's unscaled display value.
function targetDisplay(baseDisplay, unit, p) {
  if (unit === "%") return baseDisplay + clampPercent(p);   // Operator Time
  if (unit === "hz") return baseDisplay / percentToFactor(p); // LFO rate
  return baseDisplay * percentToFactor(p);                    // duration
}

// The range to automate, in clip beats. `notes` = selected notes
// [{start_time, duration}]; `clip` = {looping, loop_start, loop_end,
// start_marker, end_marker}.
function selectionRange(notes, clip) {
  if (notes && notes.length) {
    var s = Infinity, e = -Infinity;
    for (var i = 0; i < notes.length; i++) {
      s = Math.min(s, notes[i].start_time);
      e = Math.max(e, notes[i].start_time + notes[i].duration);
    }
    return { start: s, end: e, source: "notes" };
  }
  if (clip.looping) return { start: clip.loop_start, end: clip.loop_end, source: "clip" };
  return { start: clip.start_marker, end: clip.end_marker, source: "clip" };
}

// Sample times covering [start, end) on GRID.
function gridTimes(start, end, grid) {
  grid = grid || GRID;
  var out = [];
  for (var t = start; t < end - 1e-9; t += grid) out.push(t);
  return out;
}

// Merge equal consecutive samples into steps [{time, duration, value}].
// `times` are sample start times, `end` closes the last step.
function compressSteps(times, values, end) {
  var steps = [];
  for (var i = 0; i < times.length; i++) {
    var last = steps[steps.length - 1];
    if (last && last.value === values[i]) continue;
    steps.push({ time: times[i], duration: 0, value: values[i] });
  }
  for (var j = 0; j < steps.length; j++) {
    var next = j + 1 < steps.length ? steps[j + 1].time : end;
    steps[j].duration = next - steps[j].time;
  }
  return steps;
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    percentToFactor: percentToFactor,
    classifyParamName: classifyParamName,
    parseDisplay: parseDisplay,
    solveForDisplay: solveForDisplay,
    targetDisplay: targetDisplay,
    selectionRange: selectionRange,
    gridTimes: gridTimes,
    compressSteps: compressSteps,
    clampPercent: clampPercent
  };
}

// ---------------------------------------------------------------------------
// Max / Live glue (only runs inside Max's js object)
// ---------------------------------------------------------------------------

if (typeof LiveAPI !== "undefined") {
  inlets = 1;
  outlets = 1; // status text -> message box
  autowatch = 1;
}

var ready = false;  // LiveAPI is unusable until live.thisdevice bangs
var pendingP = 0;   // latest knob value
var appliedP = 0;   // knob value last written
var snap = null;    // { key, clip, range, times, targets: [...] } — pre-edit state of the selection
var applyTask = null;

function status(msg) {
  post("TimeScale: " + msg + "\n");
  outlet(0, "set", msg);
}

// live.thisdevice -> bang. The knob's restored value was already committed as
// automation in the saved set, so adopt it without re-writing anything.
function bang() {
  ready = true;
  appliedP = pendingP;
  snap = null;
  status("ready — select a MIDI clip / notes");
}

// Knob -> "scale <p>"
function scale(p) {
  pendingP = clampPercent(p);
  if (!ready || pendingP === appliedP) return;
  if (!applyTask) applyTask = new Task(apply, this);
  applyTask.cancel();
  applyTask.schedule(60); // coalesce knob drags
}

function num(x) { return Number(x instanceof Array ? x[0] : x); }
function str(x) { return String(x instanceof Array ? x.join(" ") : x); }
function cleanPath(api) { return api.path.replace(/"/g, ""); }

// LOM calls that return an object come back as ["id", N]; id 0 = None.
function apiFromCall(ret) {
  var id = ret instanceof Array ? ret[ret.length - 1] : ret;
  if (!id || Number(id) === 0) return null;
  return new LiveAPI("id " + id);
}

function displayOf(prm, raw) {
  var d = parseDisplay(str(prm.call("str_for_value", raw)));
  return d ? d.value : null;
}

function trackPath() {
  return cleanPath(new LiveAPI("this_device")).replace(/ devices \d+$/, "");
}

// The detail-view clip, if it is a MIDI clip on this device's track.
function selectedClip() {
  var clip = new LiveAPI("live_set view detail_clip");
  if (!clip.id || Number(clip.id) === 0) return null;
  if (cleanPath(clip).indexOf(trackPath() + " ") !== 0) return null;
  if (num(clip.get("is_midi_clip")) !== 1) return null;
  return clip;
}

function selectedNotes(clip) {
  try {
    var ret = clip.call("get_selected_notes_extended");
    var parsed = JSON.parse(str(ret));
    return parsed.notes || [];
  } catch (e) {
    return [];
  }
}

// First instrument after this device on the same track.
function findInstrument() {
  var me = cleanPath(new LiveAPI("this_device"));
  var tp = trackPath();
  var myIndex = parseInt(/ devices (\d+)$/.exec(me)[1], 10);
  var n = new LiveAPI(tp).getcount("devices");
  for (var i = myIndex + 1; i < n; i++) {
    var dev = new LiveAPI(tp + " devices " + i);
    if (num(dev.get("type")) === 1) return dev; // 1 = instrument
  }
  return null;
}

// [{ prm, name, unit }] — the instrument params this device drives.
function findTargets(dev) {
  var devName = str(dev.get("class_name"));
  var devPath = cleanPath(dev);
  var count = dev.getcount("parameters");
  var out = [];
  for (var i = 0; i < count; i++) {
    var prm = new LiveAPI(devPath + " parameters " + i);
    if (num(prm.get("is_quantized")) === 1) continue;
    var name = str(prm.get("name"));
    var d = parseDisplay(str(prm.call("str_for_value", num(prm.get("value")))));
    if (!d) continue;

    if (devName === "Operator" && name === "Time" && d.unit === "%") {
      out.push({ prm: prm, name: name, unit: "%" });
      continue;
    }
    var kind = classifyParamName(name);
    if (kind === "rate" && d.unit === "hz") out.push({ prm: prm, name: name, unit: "hz" });
    // Operator: envelopes are covered by its Time knob, so skip them individually.
    else if (kind === "time" && d.unit === "ms" && devName !== "Operator") out.push({ prm: prm, name: name, unit: "ms" });
  }
  return { devName: devName, targets: out };
}

// Capture the selection's current automation (or static value) for every
// target so knob moves always scale from the original, never compound.
function takeSnapshot() {
  var clip = selectedClip();
  if (!clip) { status("select a MIDI clip on this track"); return null; }
  var dev = findInstrument();
  if (!dev) { status("no instrument after this device"); return null; }

  var info = {
    looping: num(clip.get("looping")) === 1,
    loop_start: num(clip.get("loop_start")),
    loop_end: num(clip.get("loop_end")),
    start_marker: num(clip.get("start_marker")),
    end_marker: num(clip.get("end_marker"))
  };
  var range = selectionRange(selectedNotes(clip), info);
  var times = gridTimes(range.start, range.end);
  var found = findTargets(dev);

  var targets = [];
  for (var i = 0; i < found.targets.length; i++) {
    var t = found.targets[i];
    var env = apiFromCall(clip.call("automation_envelope", "id", t.prm.id));
    var base = [];
    var current = num(t.prm.get("value"));
    for (var j = 0; j < times.length; j++) {
      base.push(env ? num(env.call("value_at_time", times[j])) : current);
    }
    targets.push({ prm: t.prm, name: t.name, unit: t.unit, hadEnvelope: !!env, base: base,
                   min: num(t.prm.get("min")), max: num(t.prm.get("max")) });
  }

  return {
    key: cleanPath(clip) + "@" + range.start + "-" + range.end,
    clip: clip, range: range, times: times, devName: found.devName, targets: targets
  };
}

function currentKey() {
  var clip = selectedClip();
  if (!clip) return null;
  // Range can change with the note selection; recompute cheaply.
  var info = {
    looping: num(clip.get("looping")) === 1,
    loop_start: num(clip.get("loop_start")), loop_end: num(clip.get("loop_end")),
    start_marker: num(clip.get("start_marker")), end_marker: num(clip.get("end_marker"))
  };
  var r = selectionRange(selectedNotes(clip), info);
  return cleanPath(clip) + "@" + r.start + "-" + r.end;
}

function scaledRaw(t, raw, p, memo) {
  var key = String(raw);
  if (memo.hasOwnProperty(key)) return memo[key];
  var baseDisp = displayOf(t.prm, raw);
  var out = raw;
  if (baseDisp !== null) {
    var want = targetDisplay(baseDisp, t.unit, p);
    var solved = solveForDisplay(function (v) { return displayOf(t.prm, v); }, t.min, t.max, want);
    if (solved !== null) out = solved;
  }
  memo[key] = out;
  return out;
}

function writeTarget(clip, range, times, t, p) {
  // Back to 0 on an envelope we created: remove it entirely.
  if (p === 0 && !t.hadEnvelope) {
    clip.call("clear_envelope", "id", t.prm.id);
    return;
  }
  var env = apiFromCall(clip.call("automation_envelope", "id", t.prm.id)) ||
            apiFromCall(clip.call("create_automation_envelope", "id", t.prm.id));
  if (!env) return;

  var memo = {};
  var values = [];
  for (var i = 0; i < t.base.length; i++) {
    values.push(p === 0 ? t.base[i] : scaledRaw(t, t.base[i], p, memo));
  }
  var steps = compressSteps(times, values, range.end);
  for (var j = 0; j < steps.length; j++) {
    env.call("insert_step", steps[j].time, steps[j].duration, steps[j].value);
  }
}

function apply() {
  var p = pendingP;
  // New clip or new note selection -> new snapshot. The previous selection
  // keeps its committed automation.
  if (!snap || snap.key !== currentKey()) {
    snap = takeSnapshot();
    if (!snap) return;
  }
  for (var i = 0; i < snap.targets.length; i++) {
    writeTarget(snap.clip, snap.range, snap.times, snap.targets[i], p);
  }
  appliedP = p;
  var r = snap.range;
  status(snap.devName + " · " + snap.targets.length + " params · " +
         r.source + " " + r.start.toFixed(2) + "–" + r.end.toFixed(2) + " · " +
         p + "% (x" + percentToFactor(p).toFixed(2) + ")");
  // Back at 0 the selection is restored; drop the snapshot so edits made now
  // become the new base.
  if (p === 0) snap = null;
}

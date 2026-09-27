// Apollo TimeScale — Max for Live MIDI Effect.
//
// One knob (-50%..+50%) that tightens or loosens the *instrument's* time-based
// parameters (envelope attack/decay/release/hold, glide, ...) on this track.
// MIDI notes are never touched.
//
//   knob p (%)  ->  time factor k = 2^(p/50)   (-50% = x0.5, 0% = x1, +50% = x2)
//
// Operator is special-cased: it already has a global "Time" knob that scales
// every envelope, so we drive that one knob instead of each envelope.
//
// Classic Max `js` is ES5 — keep this file ES5. The pure helpers at the top are
// also exported for Node so they can be unit-tested outside Live.

// ---------------------------------------------------------------------------
// Pure helpers (no Max / LiveAPI dependencies)
// ---------------------------------------------------------------------------

var P_MIN = -50;
var P_MAX = 50;

function clampPercent(p) {
  p = Number(p);
  if (isNaN(p)) return 0;
  return Math.max(P_MIN, Math.min(P_MAX, p));
}

// -50% -> 0.5, 0% -> 1, +50% -> 2. Exponential so equal knob moves feel equal.
function percentToFactor(p) {
  return Math.pow(2, clampPercent(p) / 50);
}

// Parameter names that denote a duration. Word-ish match, case-insensitive.
var TIME_NAME_RE = /(attack|decay|release|hold|delay|fade ?in|fade ?out|glide|portamento|slide time|\btime\b|\batt\b|\bdec\b|\brel\b)/i;
// Things that match the above but are not durations (or are modulation depths).
var NOT_TIME_RE = /(<|slope|shape|mode|sync|rate|freq|level|sustain|amount|\bamt\b|feedback|mix|loop|retrig|legato|on$|vel|key)/i;

function isTimeParamName(name) {
  name = String(name || "");
  return TIME_NAME_RE.test(name) && !NOT_TIME_RE.test(name);
}

// Parse a Live display string into { value, unit } where unit is "ms" or "%".
// "12.3 ms" -> 12.3 ms, "1.20 s" -> 1200 ms, "-35 %" -> -35 %. null if unparseable.
function parseDisplay(str) {
  var m = /(-?\d+(?:\.\d+)?)\s*(ms|s|%)/i.exec(String(str || ""));
  if (!m) return null;
  var v = parseFloat(m[1]);
  var u = m[2].toLowerCase();
  if (u === "s") return { value: v * 1000, unit: "ms" };
  return { value: v, unit: u };
}

// Find the raw parameter value whose *displayed* value is closest to `target`.
// `display(raw)` returns a number (ms or %) or null. Assumes display is
// monotonic over [min, max] (true for every time knob in Live's devices);
// works whether it rises or falls. Returns a raw value inside [min, max].
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

// Given a param's base display value and the knob percent, return the display
// target. Durations are multiplied; Operator's Time knob (a % offset) is added.
function targetDisplay(baseDisplay, unit, p) {
  if (unit === "%") return baseDisplay + clampPercent(p);
  return baseDisplay * percentToFactor(p);
}

// Inverse of targetDisplay: recover the unscaled base from a scaled value.
function baseFromScaled(scaledDisplay, unit, p) {
  if (unit === "%") return scaledDisplay - clampPercent(p);
  return scaledDisplay / percentToFactor(p);
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    percentToFactor: percentToFactor,
    isTimeParamName: isTimeParamName,
    parseDisplay: parseDisplay,
    solveForDisplay: solveForDisplay,
    targetDisplay: targetDisplay,
    baseFromScaled: baseFromScaled,
    clampPercent: clampPercent
  };
}

// ---------------------------------------------------------------------------
// Max / Live glue (only runs inside Max's js object)
// ---------------------------------------------------------------------------

if (typeof LiveAPI !== "undefined") {
  inlets = 1;
  outlets = 1; // status text -> [print] / comment
  autowatch = 1;
}

var ready = false;    // LiveAPI is unusable until live.thisdevice bangs
var pendingP = 0;     // latest knob value
var appliedP = 0;     // knob value the instrument currently reflects
var targets = null;   // [{ api, unit, base }] snapshot of the instrument's time params
var applyTask = null;

function status(msg) {
  post("TimeScale: " + msg + "\n");
  outlet(0, "set", msg);
}

// live.thisdevice -> "ready". The knob value restored with the set has already
// been applied to the saved instrument, so adopt it without re-applying.
function bang() {
  ready = true;
  appliedP = pendingP;
  targets = null;
  status("ready (" + appliedP + "%)");
}

// Knob -> "scale <p>"
function scale(p) {
  pendingP = clampPercent(p);
  if (!ready || pendingP === appliedP) return; // restore on load / no-op
  if (!applyTask) applyTask = new Task(apply, this);
  applyTask.cancel();
  applyTask.schedule(30); // coalesce knob drags
}

function num(x) { return Number(x instanceof Array ? x[0] : x); }
function str(x) { return String(x instanceof Array ? x.join(" ") : x); }

function displayOf(api, raw) {
  var d = parseDisplay(str(api.call("str_for_value", raw)));
  return d ? d.value : null;
}

// Locate the first instrument after this device on the same track.
function findInstrument() {
  var me = new LiveAPI("this_device");
  var trackPath = me.path.replace(/"/g, "").replace(/ devices \d+$/, "");
  var myIndex = parseInt(/ devices (\d+)$/.exec(me.path.replace(/"/g, ""))[1], 10);
  var track = new LiveAPI(trackPath);
  var n = track.getcount("devices");
  for (var i = myIndex + 1; i < n; i++) {
    var dev = new LiveAPI(trackPath + " devices " + i);
    if (num(dev.get("type")) === 1) return dev; // 1 = instrument
  }
  return null;
}

// Snapshot the instrument's time params, normalised back to 0% so a knob that
// was already non-zero (e.g. restored from a saved set) doesn't compound.
function snapshot() {
  var dev = findInstrument();
  if (!dev) { status("no instrument after this device"); return null; }
  var devName = str(dev.get("class_name"));
  var devPath = dev.path.replace(/"/g, "");
  var count = dev.getcount("parameters");
  var list = [];
  var operatorTime = null;

  for (var i = 0; i < count; i++) {
    var prm = new LiveAPI(devPath + " parameters " + i);
    var name = str(prm.get("name"));
    if (num(prm.get("is_quantized")) === 1) continue;
    if (devName === "Operator" && name === "Time") { operatorTime = prm; break; }
    if (!isTimeParamName(name)) continue;
    var d = parseDisplay(str(prm.call("str_for_value", num(prm.get("value")))));
    if (!d || d.unit !== "ms") continue; // only real durations
    list.push({ api: prm, name: name, unit: "ms", base: baseFromScaled(d.value, "ms", appliedP) });
  }

  if (devName === "Operator") {
    if (!operatorTime) { status("Operator 'Time' knob not found"); return null; }
    var od = parseDisplay(str(operatorTime.call("str_for_value", num(operatorTime.get("value")))));
    list = [{ api: operatorTime, name: "Time", unit: "%", base: baseFromScaled(od ? od.value : 0, "%", appliedP) }];
  }

  status(devName + ": " + list.length + " time param(s)");
  return list;
}

function apply() {
  var p = pendingP;
  if (!targets) targets = snapshot();
  if (!targets) return;

  for (var i = 0; i < targets.length; i++) {
    var t = targets[i];
    var min = num(t.api.get("min"));
    var max = num(t.api.get("max"));
    var want = targetDisplay(t.base, t.unit, p);
    var raw = solveForDisplay(function (v) { return displayOf(t.api, v); }, min, max, want);
    if (raw !== null) t.api.set("value", raw);
  }
  appliedP = p;

  // Back at 0: forget the snapshot so manual edits made now become the new base.
  if (p === 0) targets = null;
  status(p + "% (x" + percentToFactor(p).toFixed(2) + ")");
}

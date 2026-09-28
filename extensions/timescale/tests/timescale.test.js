// Run: node --test extensions/timescale/tests/timescale.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const ts = require("../apollo_timescale.js");

test("knob maps -50/0/+50 to half/unity/double", () => {
  assert.equal(ts.percentToFactor(-50), 0.5);
  assert.equal(ts.percentToFactor(0), 1);
  assert.equal(ts.percentToFactor(50), 2);
  assert.equal(ts.percentToFactor(999), 2); // clamped
});

test("param classification: durations, rates, and exclusions", () => {
  for (const n of ["Ae Attack", "Env 1 Decay", "Amp Release", "Glide Time", "Hold", "Fe Attack", "Time"]) {
    assert.equal(ts.classifyParamName(n), "time", n);
  }
  for (const n of ["LFO Rate", "LFO 1 Rate", "LFO1 Speed", "LFO Freq"]) {
    assert.equal(ts.classifyParamName(n), "rate", n);
  }
  for (const n of ["Ae Sustain", "Attack Slope", "Time < Key", "Att < Vel", "Filter Freq",
                   "Env Loop", "LFO Sync", "Rate < Key", "LFO Amount"]) {
    assert.equal(ts.classifyParamName(n), null, n);
  }
});

test("display parsing normalises units", () => {
  assert.deepEqual(ts.parseDisplay("12.3 ms"), { value: 12.3, unit: "ms" });
  assert.deepEqual(ts.parseDisplay("1.20 s"), { value: 1200, unit: "ms" });
  assert.deepEqual(ts.parseDisplay("2.50 Hz"), { value: 2.5, unit: "hz" });
  assert.deepEqual(ts.parseDisplay("1.2 kHz"), { value: 1200, unit: "hz" });
  assert.deepEqual(ts.parseDisplay("-35 %"), { value: -35, unit: "%" });
  assert.equal(ts.parseDisplay("1/4"), null); // synced LFO -> skipped
  assert.equal(ts.parseDisplay("Off"), null);
});

test("solver inverts a non-linear (exponential) knob", () => {
  const disp = (v) => 0.1 * Math.pow(200000, v); // 0.1 ms .. 20 s
  const raw = ts.solveForDisplay(disp, 0, 1, 250);
  assert.ok(Math.abs(disp(raw) - 250) < 0.01);
  assert.equal(ts.solveForDisplay(disp, 0, 1, 1e9), 1);
  assert.equal(ts.solveForDisplay(disp, 0, 1, 0), 0);
});

test("solver handles falling knobs", () => {
  const disp = (v) => 100 - v * 50;
  const raw = ts.solveForDisplay(disp, 0, 1, 80);
  assert.ok(Math.abs(disp(raw) - 80) < 1e-4);
});

test("durations multiply, rates divide, Operator Time offsets", () => {
  assert.equal(ts.targetDisplay(100, "ms", 50), 200);
  assert.equal(ts.targetDisplay(100, "ms", -50), 50);
  assert.equal(ts.targetDisplay(4, "hz", 50), 2);   // longer shape -> slower LFO
  assert.equal(ts.targetDisplay(4, "hz", -50), 8);
  assert.equal(ts.targetDisplay(10, "%", -30), -20);
  assert.equal(ts.targetDisplay(123, "ms", 0), 123);
});

test("selection range: selected notes span, else loop, else markers", () => {
  const clip = { looping: true, loop_start: 0, loop_end: 8, start_marker: 1, end_marker: 5 };
  assert.deepEqual(ts.selectionRange([{ start_time: 2, duration: 1 }, { start_time: 0.5, duration: 0.25 }], clip),
    { start: 0.5, end: 3, source: "notes" });
  assert.deepEqual(ts.selectionRange([], clip), { start: 0, end: 8, source: "clip" });
  assert.deepEqual(ts.selectionRange([], { ...clip, looping: false }), { start: 1, end: 5, source: "clip" });
});

test("steps cover exactly the range and nothing beyond it", () => {
  const times = ts.gridTimes(1, 2, 0.25);
  assert.deepEqual(times, [1, 1.25, 1.5, 1.75]);
  const steps = ts.compressSteps(times, [5, 5, 7, 7], 2);
  assert.deepEqual(steps, [
    { time: 1, duration: 0.5, value: 5 },
    { time: 1.5, duration: 0.5, value: 7 },
  ]);
  const last = steps[steps.length - 1];
  assert.equal(last.time + last.duration, 2); // ends exactly at range end
  // Constant automation collapses to a single step.
  assert.equal(ts.compressSteps(times, [3, 3, 3, 3], 2).length, 1);
});

// Run: node --test extensions/timescale/tests
const test = require("node:test");
const assert = require("node:assert/strict");
const ts = require("../apollo_timescale.js");

test("knob maps -50/0/+50 to half/unity/double", () => {
  assert.equal(ts.percentToFactor(-50), 0.5);
  assert.equal(ts.percentToFactor(0), 1);
  assert.equal(ts.percentToFactor(50), 2);
  assert.equal(ts.percentToFactor(999), 2); // clamped
});

test("time-param classification", () => {
  for (const n of ["Ae Attack", "Env 1 Decay", "Amp Release", "Glide Time", "Hold", "Fe Attack", "Time"]) {
    assert.ok(ts.isTimeParamName(n), n);
  }
  for (const n of ["Ae Sustain", "LFO Rate", "Attack Slope", "Time < Key", "Att < Vel", "Filter Freq", "Env Loop"]) {
    assert.ok(!ts.isTimeParamName(n), n);
  }
});

test("display parsing normalises seconds to ms", () => {
  assert.deepEqual(ts.parseDisplay("12.3 ms"), { value: 12.3, unit: "ms" });
  assert.deepEqual(ts.parseDisplay("1.20 s"), { value: 1200, unit: "ms" });
  assert.deepEqual(ts.parseDisplay("-35 %"), { value: -35, unit: "%" });
  assert.equal(ts.parseDisplay("Off"), null);
});

test("solver inverts a non-linear (exponential) knob", () => {
  // Typical Live envelope knob: raw 0..1 -> 0.1 ms .. 20 s, exponential.
  const disp = (v) => 0.1 * Math.pow(200000, v);
  const raw = ts.solveForDisplay(disp, 0, 1, 250);
  assert.ok(Math.abs(disp(raw) - 250) < 0.01);
  // Out-of-range targets clamp to the ends.
  assert.equal(ts.solveForDisplay(disp, 0, 1, 1e9), 1);
  assert.equal(ts.solveForDisplay(disp, 0, 1, 0), 0);
});

test("solver handles falling knobs", () => {
  const disp = (v) => 100 - v * 50;
  const raw = ts.solveForDisplay(disp, 0, 1, 80);
  assert.ok(Math.abs(disp(raw) - 80) < 1e-4);
});

test("durations scale, Operator Time offsets, and round-trip", () => {
  assert.equal(ts.targetDisplay(100, "ms", 50), 200);
  assert.equal(ts.targetDisplay(100, "ms", -50), 50);
  assert.equal(ts.targetDisplay(10, "%", -30), -20);
  for (const p of [-50, -17, 0, 33, 50]) {
    assert.ok(Math.abs(ts.baseFromScaled(ts.targetDisplay(80, "ms", p), "ms", p) - 80) < 1e-9);
    assert.equal(ts.baseFromScaled(ts.targetDisplay(5, "%", p), "%", p), 5);
  }
});

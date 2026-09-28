// Run: npm test  (node --test with native TypeScript stripping)
import test from "node:test";
import assert from "node:assert/strict";
import {
  outsideRanges,
  parseDialogResult,
  pickInstrumentIndex,
  planChanges,
  type ParamInfo,
} from "../src/core.ts";

const param = (name: string, value: number, min = 0, max = 20000, isQuantized = false): ParamInfo =>
  ({ name, value, min, max, isQuantized });

test("instrument is the first device that isn't a MIDI effect", () => {
  assert.equal(pickInstrumentIndex(["Arpeggiator", "Chord", "Wavetable", "Reverb"]), 2);
  assert.equal(pickInstrumentIndex(["Operator"]), 0);
  assert.equal(pickInstrumentIndex(["Arpeggiator"]), -1);
});

test("real-unit durations multiply, rates divide, clamped to range", () => {
  const changes = planChanges("Wavetable", [
    param("Env 1 Attack", 100),
    param("Env 1 Sustain", 0.5, 0, 1),
    param("LFO 1 Rate", 4, 0.01, 40),
    param("Amp Release", 15000),
  ], 50);
  assert.deepEqual(changes, [
    { name: "Env 1 Attack", kind: "time", from: 100, to: 200 },
    { name: "LFO 1 Rate", kind: "rate", from: 4, to: 2 },
    { name: "Amp Release", kind: "time", from: 15000, to: 20000 }, // clamped at max
  ]);
});

test("normalised params are reported, not guessed", () => {
  const [c] = planChanges("Analog", [param("Amp Attack", 0.3, 0, 1)], 20);
  assert.equal(c.kind, "skipped");
});

test("quantized params are ignored", () => {
  assert.deepEqual(planChanges("Drift", [param("Env Attack", 3, 0, 10, true)], 20), []);
});

test("Operator: drives the global Time knob, skips individual envelopes", () => {
  const changes = planChanges("Operator", [
    param("Time", 0, -1, 1), // internal -1..1 ↔ -100..+100 %, currently 0 %
    param("Ae Attack", 100),
    param("LFO Rate", 4, 0.01, 40),
  ], -30);
  assert.equal(changes.length, 2);
  assert.equal(changes[0].kind, "operator-time");
  assert.ok(changes[0].kind === "operator-time" && Math.abs(changes[0].to - -0.3) < 1e-9);
  assert.deepEqual(changes[1], { name: "LFO Rate", kind: "rate", from: 4, to: 4 / Math.pow(2, -30 / 50) });
});

test("Operator Time offset clamps at ±100%", () => {
  const [c] = planChanges("Operator", [param("Time", 0.9, -1, 1)], 50);
  assert.ok(c.kind === "operator-time" && c.to === 1);
});

test("duplicate keeps only the selection", () => {
  assert.deepEqual(outsideRanges(8, 12, 32), [[0, 8], [12, 32]]);
  assert.deepEqual(outsideRanges(0, 12, 12), []);
});

test("dialog result parsing", () => {
  assert.equal(parseDialogResult(""), null);           // cancel
  assert.equal(parseDialogResult('{"percent":0}'), null); // no-op
  assert.equal(parseDialogResult('{"percent":25}'), 25);
  assert.equal(parseDialogResult('{"percent":90}'), 50);  // clamped
  assert.equal(parseDialogResult("garbage"), null);
});

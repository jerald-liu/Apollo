// Derived from apollo/synth/spec.py + manifest.py — update spec.py first, then re-derive.
// SPEC_VERSION "1.1" (Phase 7); N_OPERATORS = 3 (fixed — 4-op is deferred to SEED-009).
// BOUNDS values copied verbatim from apollo/synth/manifest.py constants (lines 67-77).

const SPEC_VERSION = "1.1";
const N_OPERATORS = 3;

const ALGORITHMS = {STACK: 0, PARALLEL_MODS: 1, CARRIER_PAIR: 2};

const BOUNDS = {
  ratio:     [0.5, 12.0],   // manifest.py RATIO_MIN/MAX
  level:     [0.0,  1.0],   // manifest.py LEVEL_MIN/MAX
  attack:    [0.0,  2.0],   // manifest.py ADSR_MIN/MAX
  decay:     [0.0,  2.0],   // manifest.py ADSR_MIN/MAX
  sustain:   [0.0,  1.0],   // manifest.py SUSTAIN_MIN/MAX
  release:   [0.0,  2.0],   // manifest.py ADSR_MIN/MAX
  gain:      [0.0,  1.0],   // manifest.py GAIN_MIN/MAX
  lfo_rate:  [0.05, 20.0],  // manifest.py LFO_RATE_MIN/MAX
  lfo_depth: [0.0,  1.0],   // manifest.py LFO_DEPTH_MIN/MAX
};

const LFO_WAVES   = {SINE: 0, TRIANGLE: 1, SQUARE: 2};
const LFO_TARGETS = {LEVEL: 0, PITCH: 1};

/**
 * Validate that `value` is within the bounds for `field`.
 * Returns true if valid, false if out-of-range or non-finite.
 * Mirrors apollo/synth/manifest.py _check_number (T-05-01 dual validation).
 */
function checkBounds(value, field) {
  const b = BOUNDS[field]; if (!b) return true;
  if (typeof value !== 'number' || !isFinite(value)) return false;
  return value >= b[0] && value <= b[1];
}

/**
 * synth.js — Apollo 3-operator v1.1 Web Audio FM engine.
 *
 * Mirrors apollo/synth/spec.py exactly for audition/preview purposes (D-15/D-16).
 * NOT the canonical renderer — call.wav is always produced server-side.
 *
 * Algorithms (from spec.py Algorithm IntEnum):
 *   STACK(0):         op3 → op2 → op1 (sole carrier)
 *   PARALLEL_MODS(1): (op2 + op3) → op1 (sole carrier)
 *   CARRIER_PAIR(2):  op3 → op1; op2 is an independent additive carrier
 *
 * Modulator amplitude: op_level * freq (DX-style index — modulation depth ∝ pitch).
 * ADSR:      Web Audio AudioParam scheduled ramps (linearRampToValueAtTime).
 * LFO:       New OscillatorNode per note (phase reset per onset; mirrors os.osc per-voice).
 * Tremolo:   lvl_mod = 1 - depth*(1 - lfo_uni)  → gain swings in [1-depth, 1]
 * Vibrato:   linear approx: freq offset ≈ freq*depth*50/1200*Math.LN2*lfo_bi (D-15)
 *
 * Dependencies (must be loaded before this file):
 *   spec_constants.js  → ALGORITHMS, LFO_TARGETS, LFO_WAVES
 *
 * Exports (attached to window):
 *   window.ApolloSynth = { midiToHz, applyAdsr, playNote, attachLfo, playSequence }
 */

(function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // midiToHz
  // ---------------------------------------------------------------------------

  /**
   * Convert a MIDI pitch number to Hz.
   * A4 (MIDI 69) = 440 Hz.
   */
  function midiToHz(pitch) {
    return 440 * Math.pow(2, (pitch - 69) / 12);
  }

  // ---------------------------------------------------------------------------
  // applyAdsr
  // ---------------------------------------------------------------------------

  /**
   * Schedule ADSR automation on a GainNode's gain AudioParam.
   *
   * Mirrors Faust en.adsr(attack, decay, sustain, release, gate) for audition.
   * Uses linear ramps (en.adsr uses exponential shapes; acceptable for D-15).
   *
   * @param {AudioParam} gainParam   - The .gain of a GainNode.
   * @param {object}     op          - Operator with {attack, decay, sustain, release}.
   * @param {number}     when        - AudioContext time for note onset.
   * @param {number}     noteDuration - Time from onset to note-off (seconds).
   */
  function applyAdsr(gainParam, op, when, noteDuration) {
    gainParam.cancelScheduledValues(when);
    gainParam.setValueAtTime(0, when);
    gainParam.linearRampToValueAtTime(1.0, when + op.attack);
    gainParam.linearRampToValueAtTime(op.sustain, when + op.attack + op.decay);
    gainParam.setValueAtTime(op.sustain, when + noteDuration);
    gainParam.linearRampToValueAtTime(0, when + noteDuration + op.release);
  }

  // ---------------------------------------------------------------------------
  // attachLfo
  // ---------------------------------------------------------------------------

  /**
   * Attach a global LFO (from patch.lfo) to all carriers.
   *
   * Creates a NEW OscillatorNode per playNote call so LFO phase resets at
   * each note onset — matches Faust os.osc per-polyphonic-voice reset.
   *
   * TREMOLO (target=0, LFO_TARGETS.LEVEL):
   *   lvl_mod = 1 - depth*(1-lfo_uni)  →  constant (1-depth/2) + lfo_bi*(depth/2)
   *   Carrier gain swings in [1-depth, 1].
   *   Implementation: set carrier gainNode.gain to 0, drive it with a ConstantSource
   *   (DC = level*(1-depth/2)) plus a scaled LFO (amplitude = level*(depth/2)).
   *
   * VIBRATO (target=1, LFO_TARGETS.PITCH):
   *   pitch_mul = pow(2, lfo_bi*depth*50/1200)
   *   Audition linear approx (D-15 allows): freq offset ≈ freq*depth*50/1200*Math.LN2
   *   Connect one scaled LFO GainNode to all carrier osc.frequency AudioParams.
   *
   * @param {AudioContext} audioCtx
   * @param {object}       patch     - Full patch object; uses patch.lfo.
   * @param {Array}        carriers  - [{gainNode, osc, level}, ...]
   * @param {number}       freq      - Base frequency in Hz for this note.
   * @param {number}       when      - AudioContext time for note onset.
   * @param {number}       duration  - Note duration in seconds (for osc.stop).
   */
  function attachLfo(audioCtx, patch, carriers, freq, when, duration) {
    if (!patch.lfo) return;

    const { rate, depth, wave, target } = patch.lfo;

    // Create a fresh OscillatorNode — phase resets at `when` (per-note phase reset).
    const lfoOsc = audioCtx.createOscillator();
    lfoOsc.frequency.value = rate;
    lfoOsc.type = ['sine','triangle','square'][wave];
    lfoOsc.start(when);
    lfoOsc.stop(when + duration + 0.2);

    if (target === LFO_TARGETS.LEVEL) {
      // TREMOLO: drive each carrier's gainNode.gain with:
      //   DC component:  level * (1 - depth/2)
      //   LFO component: level * (depth/2) * lfo_bi
      // Together: level * [1 - depth/2 + (depth/2)*lfo_bi]
      //         = level * [1 - depth*(1 - lfo_uni)]   (== the spec formula)
      carriers.forEach(function (c) {
        // Override the carrier gainNode's static value with AudioParam summation.
        c.gainNode.gain.value = 0;

        // DC offset: constant level*(1-depth/2).
        var dc = audioCtx.createConstantSource();
        dc.offset.value = c.level * (1 - depth / 2);
        dc.connect(c.gainNode.gain);
        dc.start(when);

        // LFO component: lfoOsc → scaled gain → gainNode.gain.
        var lg = audioCtx.createGain();
        lg.gain.value = c.level * (depth / 2);
        lfoOsc.connect(lg);
        lg.connect(c.gainNode.gain);
      });
    } else {
      // VIBRATO (target === LFO_TARGETS.PITCH):
      // Linear approx of pow(2, lfo_bi*depth*50/1200):
      //   maxDeviation = freq * depth * 50/1200 * ln(2)
      // Connect one scaled LFO to all carrier osc.frequency AudioParams.
      var maxDev = freq * depth * 50 / 1200 * Math.LN2;
      var lg = audioCtx.createGain();
      lg.gain.value = maxDev;
      lfoOsc.connect(lg);
      carriers.forEach(function (c) {
        lg.connect(c.osc.frequency);
      });
    }
  }

  // ---------------------------------------------------------------------------
  // playNote
  // ---------------------------------------------------------------------------

  /**
   * Build and schedule a 3-operator FM note through the Web Audio graph.
   *
   * Topology (mirrors spec.py _body_no_lfo / _body_lfo_*):
   *   - ops[0] = operator 1 (1-based DSP numbering), ops[1] = op2, ops[2] = op3
   *   - Modulator signal amplitude = op_level * freq  (DX-style index ∝ pitch)
   *   - Connected to target oscillator's .frequency AudioParam (adds Hz offset)
   *
   * STACK(0):
   *   wireMod(ops[2].env, ops[1].osc.frequency, ops[2].level)   // op3 → op2
   *   wireMod(ops[1].env, ops[0].osc.frequency, ops[1].level)   // op2 → op1
   *   carriers = [op1]
   *
   * PARALLEL_MODS(1):
   *   wireMod(ops[1].env, ops[0].osc.frequency, ops[1].level)   // op2 → op1
   *   wireMod(ops[2].env, ops[0].osc.frequency, ops[2].level)   // op3 → op1
   *   carriers = [op1]
   *
   * CARRIER_PAIR(2):
   *   wireMod(ops[2].env, ops[0].osc.frequency, ops[2].level)   // op3 → op1
   *   carriers = [op1, op2]  (op2 is an independent additive carrier)
   *
   * @param {AudioContext}   audioCtx
   * @param {object}         patch      - call_fm.json object.
   * @param {number}         pitch      - MIDI pitch (0-127).
   * @param {number}         velocity   - MIDI velocity (0-127).
   * @param {number}         when       - AudioContext time for note onset.
   * @param {number}         duration   - Note duration (seconds, note-off time).
   * @param {AudioNode|null} master     - Destination node (default: audioCtx.destination).
   */
  function playNote(audioCtx, patch, pitch, velocity, when, duration, master) {
    var freq = midiToHz(pitch);
    var dest = master || audioCtx.destination;

    // Note-level output gain (patch.gain * velocity scaling).
    var noteGain = audioCtx.createGain();
    noteGain.gain.value = patch.gain * (velocity / 127);
    noteGain.connect(dest);

    // Build one {osc, env, level} bundle per operator.
    var ops = patch.operators.map(function (op) {
      var osc = audioCtx.createOscillator();
      osc.type = 'sine';
      osc.frequency.value = freq * op.ratio;

      var env = audioCtx.createGain();
      applyAdsr(env.gain, op, when, duration);

      osc.connect(env);
      osc.start(when);
      osc.stop(when + duration + op.release + 0.05);

      return { osc: osc, env: env, level: op.level };
    });

    // wireMod: connect a modulator's envelope output (scaled by op_level*freq)
    // to a destination AudioParam (the carrier osc's .frequency).
    // This implements the DX-style modulation index that scales with pitch.
    function wireMod(srcEnv, dstParam, level) {
      var g = audioCtx.createGain();
      g.gain.value = level * freq;
      srcEnv.connect(g);
      g.connect(dstParam);
    }

    // wireCarrier: connect an operator's envelope to noteGain via a level-scaling
    // GainNode.  Returns the carrier gain node so the LFO can target it.
    function wireCarrier(env, level) {
      var cg = audioCtx.createGain();
      cg.gain.value = level;
      env.connect(cg);
      cg.connect(noteGain);
      return cg;
    }

    var carriers = [];

    var alg = patch.algorithm;
    if (alg === ALGORITHMS.STACK) {
      // op3 modulates op2; op2 modulates op1; op1 is the sole carrier.
      wireMod(ops[2].env, ops[1].osc.frequency, ops[2].level);
      wireMod(ops[1].env, ops[0].osc.frequency, ops[1].level);
      carriers = [
        { gainNode: wireCarrier(ops[0].env, ops[0].level), osc: ops[0].osc, level: ops[0].level }
      ];
    } else if (alg === ALGORITHMS.PARALLEL_MODS) {
      // op2 and op3 both modulate op1; op1 is the sole carrier.
      wireMod(ops[1].env, ops[0].osc.frequency, ops[1].level);
      wireMod(ops[2].env, ops[0].osc.frequency, ops[2].level);
      carriers = [
        { gainNode: wireCarrier(ops[0].env, ops[0].level), osc: ops[0].osc, level: ops[0].level }
      ];
    } else {
      // CARRIER_PAIR: op3 modulates op1; op2 is an independent additive carrier.
      wireMod(ops[2].env, ops[0].osc.frequency, ops[2].level);
      carriers = [
        { gainNode: wireCarrier(ops[0].env, ops[0].level), osc: ops[0].osc, level: ops[0].level },
        { gainNode: wireCarrier(ops[1].env, ops[1].level), osc: ops[1].osc, level: ops[1].level }
      ];
    }

    // Attach optional LFO (tremolo or vibrato).
    attachLfo(audioCtx, patch, carriers, freq, when, duration);
  }

  // ---------------------------------------------------------------------------
  // playSequence
  // ---------------------------------------------------------------------------

  /**
   * Play a sequence of notes (from the /midi/<nnn>/<file> JSON endpoint) through
   * the browser FM synth using the given patch.
   *
   * All notes share a common master gain node so they form a single group that
   * connects to audioCtx.destination.
   *
   * @param {AudioContext} audioCtx
   * @param {object}       patch   - call_fm.json patch object.
   * @param {Array}        notes   - [{pitch, velocity, start, duration}, ...] (seconds).
   */
  function playSequence(audioCtx, patch, notes) {
    var t0 = audioCtx.currentTime + 0.05;
    var master = audioCtx.createGain();
    master.gain.value = 1;
    master.connect(audioCtx.destination);
    notes.forEach(function (n) {
      playNote(audioCtx, patch, n.pitch, n.velocity, t0 + n.start, n.duration, master);
    });
  }

  // ---------------------------------------------------------------------------
  // Export
  // ---------------------------------------------------------------------------

  window.ApolloSynth = {
    midiToHz: midiToHz,
    applyAdsr: applyAdsr,
    playNote: playNote,
    attachLfo: attachLfo,
    playSequence: playSequence,
  };

}());

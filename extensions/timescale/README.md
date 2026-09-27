# Apollo TimeScale (Max for Live MIDI Effect)

One knob, **Time Scale** from −50% to +50%. It tightens or loosens the playback shape
of the instrument on this MIDI track by scaling its time-based parameters. MIDI
notes are never changed.

| Knob | Time factor | Feel |
|---|---|---|
| −50% | ×0.5 | tighter, snappier |
| 0% | ×1 | unchanged |
| +50% | ×2 | looser, longer tails |

The mapping is exponential (`k = 2^(p/50)`), so equal knob moves sound like equal changes.

## What it scales

- **Operator:** only Operator's global **Time** knob, which already scales every
  envelope. The knob percent is added to Operator's Time value.
- **Any other instrument:** the first instrument after this device on the track.
  It scales every continuous parameter whose name looks like a duration (Attack,
  Decay, Release, Hold, Delay, Fade, Glide, Time) *and* whose display unit is ms or s.
  Levels (Sustain), rates, slopes and modulation amounts (`Time < Vel`) are skipped.

Targets are solved in the *displayed* units (ms), so non-linear knobs scale correctly.

## Install

1. In Live, drop a **Max MIDI Effect** on a MIDI track, before the instrument, and click Edit.
2. In Max, open `Apollo TimeScale.maxpat` and copy all of it into the device.
   Alternatively, build it by hand: `live.dial` → `prepend scale` → `deferlow` → `js apollo_timescale.js`, and
   `live.thisdevice` → `t b b` (right outlet → dial, left outlet → `deferlow`).
3. Put `apollo_timescale.js` next to the saved `.amxd`, or freeze the device.
4. Save the device as `Apollo TimeScale.amxd`.

## Behaviour notes / v1 limits

- The instrument's current values are captured when the knob leaves 0%.
  Edits you make to the instrument while the knob is off 0 are overwritten on the next knob move.
  Return the knob to 0, edit, then scale again.
- Only the top-level instrument is handled. Instruments nested inside Instrument
  Racks are not handled yet.
- Every knob move writes the instrument's parameters, so each drag adds undo steps.
- Test Operator's Time mapping by ear. It adds the knob % to Time's %, and Operator's
  internal Time curve may not be exactly ×0.5 to ×2 at ±50%.

## Tests

The pure helpers (mapping, name classifier, display parser, solver) run in Node:

```
node --test extensions/timescale/tests/timescale.test.js
```

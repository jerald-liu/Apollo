# Apollo TimeScale (Max for Live MIDI Effect)

One knob, **Time Scale** from −50% to +50%. It tightens or loosens the playback shape
of the instrument on this MIDI track. The result is **written as clip automation over
the selected range**, so it is committed into the clip. Everything outside the range is
left alone: at the end of the range each parameter returns to what it was before.
MIDI notes are never changed.

| Knob | Time factor | Envelope times | LFO rates | Feel |
|---|---|---|---|---|
| −50% | ×0.5 | halved | doubled | tighter, snappier |
| 0% | ×1 | unchanged | unchanged | — |
| +50% | ×2 | doubled | halved | looser, longer |

The mapping is exponential (`k = 2^(p/50)`), so equal knob moves sound like equal changes.

## Workflow

1. Put the device on a MIDI track, before the instrument.
2. Open a MIDI clip on that track in the detail view.
3. Optionally select some notes. The **selected range** is the span of the selected notes.
   With no notes selected, it is the whole clip (the loop region if the clip loops).
4. Turn the knob. Clip automation is written for every affected parameter, in that range only.
   Turn it back to 0% to restore the range exactly.
5. Select another clip or other notes and repeat. Each selection keeps its own committed automation.

## What it scales

- **Durations** (display in ms/s), multiplied by k: Attack, Decay, Release, Hold, Delay, Fade, Glide, Time.
- **LFO rates** (display in Hz), divided by k: Rate, Speed, LFO Freq. Tempo-synced rates
  (`1/4` and similar) are skipped.
- **Operator:** envelopes are driven through its global **Time** knob (knob % added to
  Time's %) instead of one by one. Its LFO Rate is scaled like any other rate.
- Skipped: Sustain, levels, slopes, modulation amounts (`Time < Vel`), sync/mode switches.

Values are solved in the *displayed* units (ms, Hz), so non-linear knobs scale correctly.
If the clip already has automation for a parameter, that automation is re-scaled point by
point on a 1/16-note grid, not flattened.

## Install

1. In Live, drop a **Max MIDI Effect** on a MIDI track, before the instrument, and click Edit.
2. In Max, open `Apollo TimeScale.maxpat` and copy all of it into the device.
   Alternatively, build it by hand: `live.dial` → `prepend scale` → `deferlow` → `js apollo_timescale.js`, and
   `live.thisdevice` → `t b b` (right outlet → dial, left outlet → `deferlow`).
3. Put `apollo_timescale.js` next to the saved `.amxd`, or freeze the device.
4. Save the device as `Apollo TimeScale.amxd`.

## Behaviour notes / v1 limits

- **Release of the last note.** The range ends where the last selected note ends, so the
  release tail after that note-off plays at the *original* release time. Select up to the
  next note, or the whole clip, if you want the tail scaled too.
- **Scaling stacks across selections.** The knob scales from the state captured when you
  first touch it on a selection. If you reselect a range you already scaled, it starts
  from the scaled automation.
- **Removing automation.** Returning to 0% removes envelopes the device created. Envelopes
  that existed before are restored on the grid.
- **Clip automation, not arrangement track automation.** The Live API only exposes clip
  envelopes, so the arrangement time selection isn't used.
- **Nested instruments.** Only the top-level instrument is handled, not instruments inside Instrument Racks.
- **Undo steps.** Every knob move writes automation, so each drag adds undo steps.
- **Operator's Time mapping.** Test it by ear. Operator's internal curve may not be exactly
  ×0.5 to ×2 at ±50%.

## Tests

The pure helpers (mapping, classifier, display parser, solver, range and step builder) run in Node:

```
node --test extensions/timescale/tests/timescale.test.js
```

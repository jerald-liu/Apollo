# Apollo TimeScale — Ableton Live Extension

Tightens or loosens the playback shape of the instrument on a MIDI track, for a
**selected range only**. Built on the Ableton Extensions SDK (1.0.0-beta, Live 12 Suite, 12.4.5+ beta).

- **Envelope times** (Attack, Decay, Release, Hold, Delay, Glide...) are multiplied by k.
- **LFO rates** are divided by k.
- **Operator:** its global **Time** knob is used instead of each envelope. Its LFO Rate is scaled too.

k is the time factor: −50% → ×0.5 (tighter), +50% → ×2 (looser), using `k = 2^(p/50)`.
The name classifier and the curve are shared with the Max for Live device in
[`../timescale`](../timescale) (`apollo_timescale.js`), so both behave the same.

## Use

Right-click on a MIDI track, then choose **Apollo: Time Scale…**. You can right-click either:

- an **arrangement time selection**, or
- an **arrangement MIDI clip**, which uses the clip's span as the selection.

Pick a percentage and press Apply.

## How it commits the change: split, not automation

The SDK (1.0.0-beta) **cannot write automation**, and it only exposes raw parameter
values, not "12 ms" display strings. So the extension commits the change by splitting:

1. It duplicates the track, including instrument, effects and mixer. The copy is named `Lead · TS +20%`.
2. The **duplicate keeps only the selected range**. Everything else on it is cleared, and its
   session clips are deleted so scene launches don't play notes twice.
3. The **original loses only the selected range**. Everything outside it plays exactly as before.
4. The duplicate's instrument gets its time-based parameters scaled.

A side effect: notes inside the range keep their full scaled release tails, because the
duplicate track rings out on its own.

## Limits (v1)

- **Real units only.** A parameter is scaled only when its internal value is in real units
  (range max > 1, assumed ms/Hz). Parameters stored as 0..1 have an unknown curve, so
  they're **skipped and listed** in the summary dialog. Use the Max for Live device (which
  sees display strings) to find their curves.
- **Operator's Time knob** is assumed to be linear −100%..+100% across its internal range.
  Needs a listen in Live.
- **Instrument detection:** the first device that isn't a known MIDI effect. Devices are
  matched by `device.name`, so a renamed Operator won't be recognised.
- **Notes held across the selection edge are cut** (`clearClipsInRange` truncates clips).
- **Arrangement automation** on the original track is copied to the duplicate and will
  override the scaled static values for those parameters.
- **Session clips** aren't supported. Racks aren't searched.
- **Undo:** each SDK edit is its own transaction, so undoing may take several steps.

## Develop

The SDK isn't on npm and its licence forbids redistribution, so copy the two tarballs from
your SDK zip into `vendor/`. They are gitignored.

```
cp ~/Downloads/<sdk-zip>/ableton-extensions-{sdk,cli}-1.0.0-beta.0.tgz vendor/
npm install
cp .env.example .env        # set EXTENSION_HOST_PATH (see the SDK docs)
npm test                    # unit + end-to-end tests against a fake Extension Host
npm start                   # build + run inside Live (the CLI wants Node ≥ 24.14.1)
npm run package             # → .ablx
```

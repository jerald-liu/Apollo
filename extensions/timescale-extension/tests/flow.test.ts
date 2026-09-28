// End-to-end flow against a fake Extension Host: the real SDK code runs on top
// of an in-memory Live Set, so we exercise right-click → dialog → split → scale
// without Live. Run: npm test
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import * as os from "node:os";
import * as path from "node:path";
import * as esbuild from "esbuild";

type Obj = { classes: string[]; parent: number | null; [k: string]: any };

function fakeLive(dialogResult: string) {
  let nextId = 1;
  const objs = new Map<number, Obj>();
  const add = (o: Obj) => { const id = nextId++; objs.set(id, o); return id; };
  const h = (id: number) => ({ id: BigInt(id) });
  const get = (handle: { id: bigint }) => objs.get(Number(handle.id))!;

  const app = add({ classes: ["Application"], parent: null });
  const song = add({ classes: ["Song"], parent: app, tracks: [] as number[] });
  const mkParam = (dev: number, name: string, value: number, min: number, max: number) =>
    add({ classes: ["DeviceParameter"], parent: dev, name, value, min, max, quantized: false });
  const mkTrack = (name: string) => {
    const t = add({ classes: ["MidiTrack", "Track"], parent: song, name, clips: [] as number[], slots: [] as number[], devices: [] as number[] });
    get(h(song)).tracks.push(t);
    return t;
  };

  // Original track: Arpeggiator → Wavetable, three 4-beat clips at 0, 8, 16.
  const track = mkTrack("Lead");
  for (const s of [0, 8, 16]) get(h(track)).clips.push(add({ classes: ["MidiClip", "Clip"], parent: track, start: s, end: s + 4 }));
  const slot = add({ classes: ["ClipSlot"], parent: track, clip: add({ classes: ["MidiClip", "Clip"], parent: 0, start: 0, end: 4 }) });
  get(h(track)).slots.push(slot);
  const arp = add({ classes: ["Device"], parent: track, name: "Arpeggiator", params: [] as number[] });
  const wt = add({ classes: ["Device"], parent: track, name: "Wavetable", params: [] as number[] });
  get(h(wt)).params.push(
    mkParam(wt, "Env 1 Attack", 100, 0.1, 20000),
    mkParam(wt, "Env 1 Sustain", 0.5, 0, 1),
    mkParam(wt, "LFO 1 Rate", 4, 0.01, 40),
    mkParam(wt, "Filter Freq", 1000, 20, 20000),
  );
  get(h(track)).devices.push(arp, wt);

  const commands = new Map<string, (...a: unknown[]) => void>();
  const menus: Array<[string, string, string]> = [];
  const dialogs: string[] = [];

  const clone = (id: number, parent: number): number => {
    const o = get(h(id));
    const copy: Obj = { ...o, parent };
    const cid = add(copy);
    for (const key of ["clips", "slots", "devices", "params"]) {
      if (Array.isArray(o[key])) copy[key] = o[key].map((c: number) => clone(c, cid));
    }
    if (o.classes[0] === "ClipSlot" && o.clip) copy.clip = clone(o.clip, cid);
    return cid;
  };

  const dataModel = {
    withinTransaction: <T>(fn: () => T) => fn(),
    getObjectIsOfClass: (hd: any, cls: string) => get(hd).classes.includes(cls),
    getObjectCanonicalParent: (hd: any) => { const p = get(hd).parent; return p ? h(p) : null; },
    getRoot: () => h(app),
    rootGetSong: () => h(song),
    songGetTracks: (hd: any) => get(hd).tracks.map(h),
    songDuplicateTrack: (_s: any, t: any, ok: (x: any) => void) => {
      const tracks = get(h(song)).tracks as number[];
      const dup = clone(Number(t.id), song);
      tracks.splice(tracks.indexOf(Number(t.id)) + 1, 0, dup);
      ok(h(dup));
    },
    trackGetName: (hd: any) => get(hd).name,
    trackSetName: (hd: any, v: string) => { get(hd).name = v; },
    trackGetArrangementClips: (hd: any) => get(hd).clips.map(h),
    trackGetClipSlots: (hd: any) => get(hd).slots.map(h),
    trackGetDevices: (hd: any) => get(hd).devices.map(h),
    trackClearClipsInRange: (hd: any, s: number, e: number, ok: () => void) => {
      const t = get(hd);
      t.clips = (t.clips as number[]).flatMap((c) => {
        const clip = get(h(c));
        if (clip.end <= s || clip.start >= e) return [c];
        const keep: number[] = [];
        if (clip.start < s) keep.push(add({ ...clip, end: s }));
        if (clip.end > e) keep.push(add({ ...clip, start: e }));
        return keep;
      });
      ok();
    },
    clipslotGetClip: (hd: any) => { const c = get(hd).clip; return c ? h(c) : null; },
    clipslotDeleteClip: (hd: any, ok: () => void) => { get(hd).clip = null; ok(); },
    clipGetStartTime: (hd: any) => get(hd).start,
    clipGetEndTime: (hd: any) => get(hd).end,
    deviceGetName: (hd: any) => get(hd).name,
    deviceGetParameters: (hd: any) => get(hd).params.map(h),
    deviceParameterGetName: (hd: any) => get(hd).name,
    deviceParameterGetInternalMin: (hd: any) => get(hd).min,
    deviceParameterGetInternalMax: (hd: any) => get(hd).max,
    deviceParameterGetIsQuantized: (hd: any) => get(hd).quantized,
    deviceParameterGetInternalValue: (hd: any, ok: (v: number) => void) => ok(get(hd).value),
    deviceParameterSetInternalValue: (hd: any, v: number, ok: () => void) => { get(hd).value = v; ok(); },
  };

  const activation = {
    hostApiVersion: "1.0.0",
    initializeExtensionHost: () => ({
      dataModel,
      commands: {
        registerCommand: (id: string, cb: any) => commands.set(id, cb),
        executeCommand: (id: string, ...a: unknown[]) => commands.get(id)!(...a),
      },
      environment: {},
      resources: {},
      ui: {
        registerContextMenuAction: (scope: string, title: string, cmd: string, ok: any) => { menus.push([scope, title, cmd]); ok(() => {}); },
        showModalDialog: (url: string, _w: number, _hh: number, ok: (s: string) => void) => {
          dialogs.push(decodeURIComponent(url));
          ok(dialogs.length === 1 ? dialogResult : "");
        },
      },
    }),
  };

  return { activation, commands, menus, dialogs, get, h, song, track, wt };
}

async function loadExtension() {
  const outfile = path.join(os.tmpdir(), `timescale-test-${process.pid}.cjs`);
  await esbuild.build({
    entryPoints: [new URL("../src/extension.ts", import.meta.url).pathname],
    outfile, bundle: true, format: "cjs", platform: "node", logLevel: "silent",
    loader: { ".html": "text" },
  });
  return createRequire(import.meta.url)(outfile) as { activate: (a: unknown) => void };
}

const settle = () => new Promise((r) => setTimeout(r, 20));

test("right-click an arrangement selection → split onto a scaled duplicate", async () => {
  const ext = await loadExtension();
  const live = fakeLive(JSON.stringify({ percent: 50 }));
  ext.activate(live.activation);

  assert.deepEqual(live.menus.map((m) => m[0]).sort(), ["MidiClip", "MidiTrack.ArrangementSelection"]);

  // Select beats 8–12 (the middle clip) on "Lead".
  live.commands.get("apollo-timescale.apply")!({
    time_selection_start: 8, time_selection_end: 12, selected_lanes: [live.h(live.track)],
  });
  await settle();

  const [orig, dup] = live.get(live.h(live.song)).tracks.map((t: number) => live.get(live.h(t)));
  const spans = (t: any) => t.clips.map((c: number) => { const x = live.get(live.h(c)); return [x.start, x.end]; });

  // Original: selection removed, everything else untouched.
  assert.deepEqual(spans(orig), [[0, 4], [16, 20]]);
  assert.equal(orig.name, "Lead");
  // Duplicate: only the selection, no session clips.
  assert.deepEqual(spans(dup), [[8, 12]]);
  assert.equal(dup.name, "Lead · TS +50%");
  assert.equal(live.get(live.h(dup.slots[0])).clip, null);

  // Original instrument unchanged; duplicate's instrument scaled.
  const values = (devId: number) =>
    Object.fromEntries(live.get(live.h(devId)).params.map((p: number) => [live.get(live.h(p)).name, live.get(live.h(p)).value]));
  assert.deepEqual(values(live.wt), { "Env 1 Attack": 100, "Env 1 Sustain": 0.5, "LFO 1 Rate": 4, "Filter Freq": 1000 });
  assert.deepEqual(values(dup.devices[1]), { "Env 1 Attack": 200, "Env 1 Sustain": 0.5, "LFO 1 Rate": 2, "Filter Freq": 1000 });

  // Summary dialog reports what was scaled and what was skipped.
  const summary = live.dialogs[1];
  assert.match(summary, /Wavetable · \+50%/);
  assert.match(summary, /Env 1 Attack, LFO 1 Rate/);
});

test("cancel leaves the set untouched", async () => {
  const ext = await loadExtension();
  const live = fakeLive("");
  ext.activate(live.activation);
  live.commands.get("apollo-timescale.apply")!({
    time_selection_start: 8, time_selection_end: 12, selected_lanes: [live.h(live.track)],
  });
  await settle();
  assert.equal(live.get(live.h(live.song)).tracks.length, 1);
  assert.equal(live.dialogs.length, 1);
});

test("session clips are refused with a message", async () => {
  const ext = await loadExtension();
  const live = fakeLive(JSON.stringify({ percent: 20 }));
  ext.activate(live.activation);
  const slot = live.get(live.h(live.track)).slots[0];
  const sessionClip = live.get(live.h(slot)).clip;
  live.get(live.h(sessionClip)).parent = slot;
  live.commands.get("apollo-timescale.apply")!(live.h(sessionClip));
  await settle();
  assert.equal(live.get(live.h(live.song)).tracks.length, 1);
  assert.match(live.dialogs[0], /Session clips aren't supported/);
});

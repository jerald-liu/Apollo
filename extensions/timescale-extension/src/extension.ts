// Apollo TimeScale — Ableton Live Extension.
//
// Right-click an arrangement selection (or an arrangement clip) on a MIDI track
// → "Apollo: Time Scale…" → pick -50%..+50%.
//
// The SDK (1.0.0-beta) can't write automation, so the change is committed by
// splitting: the selected range moves to a duplicate track whose instrument has
// its time-based parameters scaled. The original track is cleared in that range
// only, so everything outside the selection plays exactly as before.
import {
  initialize,
  DataModelObject,
  MidiClip,
  MidiTrack,
  TakeLane,
  ClipSlot,
  type ActivationContext,
  type ArrangementSelection,
  type ExtensionContext,
  type Handle,
} from "@ableton-extensions/sdk";
import dialogHtml from "../ui/dialog.html";
import {
  formatPercent,
  outsideRanges,
  parseDialogResult,
  percentToFactor,
  pickInstrumentIndex,
  planChanges,
  type Change,
  type ParamInfo,
} from "./core.ts";

const COMMAND = "apollo-timescale.apply";
type Ctx = ExtensionContext<"1.0.0">;
type Target = { track: MidiTrack<"1.0.0">; start: number; end: number };

export function activate(activation: ActivationContext) {
  const context = initialize(activation, "1.0.0");

  context.commands.registerCommand(COMMAND, (arg: unknown) => {
    run(context, arg).catch((err) => console.error("[TimeScale]", err));
  });
  context.ui.registerContextMenuAction("MidiTrack.ArrangementSelection", "Apollo: Time Scale…", COMMAND);
  context.ui.registerContextMenuAction("MidiClip", "Apollo: Time Scale…", COMMAND);
}

function isSelection(arg: unknown): arg is ArrangementSelection {
  return typeof arg === "object" && arg !== null && "time_selection_start" in arg && "selected_lanes" in arg;
}

function trackOf(obj: DataModelObject<"1.0.0"> | null): MidiTrack<"1.0.0"> | null {
  while (obj) {
    if (obj instanceof MidiTrack) return obj;
    if (obj instanceof ClipSlot) return null; // session clip — not supported
    obj = obj.parent;
  }
  return null;
}

// Work out which track and time range the user right-clicked.
function resolveTarget(context: Ctx, arg: unknown): Target | string {
  if (isSelection(arg)) {
    const lane = arg.selected_lanes[0];
    if (!lane) return "Select a time range on a MIDI track.";
    const obj = context.getObjectFromHandle(lane, DataModelObject);
    const track = obj instanceof TakeLane ? trackOf(obj.parent) : trackOf(obj);
    if (!track) return "Selection is not on a MIDI track.";
    if (arg.time_selection_end <= arg.time_selection_start) return "Selection is empty.";
    return { track, start: arg.time_selection_start, end: arg.time_selection_end };
  }
  const clip = context.getObjectFromHandle(arg as Handle, DataModelObject);
  if (!(clip instanceof MidiClip)) return "Not a MIDI clip.";
  const track = trackOf(clip.parent);
  if (!track) return "Session clips aren't supported yet — use an arrangement clip or selection.";
  return { track, start: clip.startTime, end: clip.endTime };
}

async function run(context: Ctx, arg: unknown) {
  const target = resolveTarget(context, arg);
  if (typeof target === "string") {
    await showMessage(context, target);
    return;
  }

  const percent = parseDialogResult(
    await context.ui.showModalDialog(`data:text/html,${encodeURIComponent(dialogHtml)}`, 340, 210),
  );
  if (percent === null) return;

  const { track, start, end } = target;
  const song = context.application.song;

  // Groups the edits for undo where the host allows. The SDK wraps each async
  // mutation in its own transaction, so Live may still show several undo steps.
  const result = await context.withinTransaction(async () => {
    const dup = (await song.duplicateTrack(track)) as MidiTrack<"1.0.0">;
    dup.name = `${track.name} · TS ${formatPercent(percent)}`;

    // Duplicate keeps only [start, end); original loses only [start, end).
    const lastEnd = Math.max(end, ...dup.arrangementClips.map((c) => c.endTime));
    for (const [s, e] of outsideRanges(start, end, lastEnd)) await dup.clearClipsInRange(s, e);
    await track.clearClipsInRange(start, end);

    // Session clips would double up on scene launch — the duplicate is arrangement-only.
    for (const slot of dup.clipSlots) if (slot.clip) await slot.deleteClip();

    return scaleInstrument(dup, percent);
  });

  await showMessage(context, summary(result, percent));
}

async function scaleInstrument(track: MidiTrack<"1.0.0">, percent: number) {
  const devices = track.devices;
  const idx = pickInstrumentIndex(devices.map((d) => d.name));
  if (idx < 0) return { device: null as string | null, changes: [] as Change[] };
  const device = devices[idx];

  const params = device.parameters;
  const infos: ParamInfo[] = await Promise.all(
    params.map(async (p) => ({
      name: p.name,
      min: p.min,
      max: p.max,
      isQuantized: p.isQuantized,
      value: await p.getValue(),
    })),
  );
  const changes = planChanges(device.name, infos, percent);
  for (const c of changes) {
    if (c.kind === "skipped") continue;
    const param = params[infos.findIndex((i) => i.name === c.name)];
    await param.setValue(c.to);
  }
  return { device: device.name, changes };
}

function summary(r: { device: string | null; changes: Change[] }, percent: number): string {
  if (!r.device) return "Split done, but no instrument was found on the track.";
  const applied = r.changes.filter((c) => c.kind !== "skipped");
  const skipped = r.changes.filter((c) => c.kind === "skipped");
  const lines = [
    `${r.device} · ${formatPercent(percent)} (time ×${percentToFactor(percent).toFixed(2)})`,
    `${applied.length} parameter(s) scaled${applied.length ? ": " + applied.map((c) => c.name).join(", ") : ""}`,
  ];
  if (skipped.length) lines.push(`${skipped.length} skipped (unknown curve): ${skipped.map((c) => c.name).join(", ")}`);
  return lines.join("\n");
}

async function showMessage(context: Ctx, text: string) {
  const html = `<!DOCTYPE html><html><body style="font:13px -apple-system,sans-serif;padding:12px;white-space:pre-wrap">${escapeHtml(text)}
<p><button onclick="(window.webkit?.messageHandlers?.live||window.chrome?.webview).postMessage({method:'close_and_send',params:['']})">OK</button></p></body></html>`;
  await context.ui.showModalDialog(`data:text/html,${encodeURIComponent(html)}`, 360, 180);
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[ch]!);
}

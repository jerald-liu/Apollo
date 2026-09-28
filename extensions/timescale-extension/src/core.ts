// Pure planning logic for the TimeScale extension. No SDK imports, so it runs
// under `node --test`. Name classification and the knob→factor curve are shared
// with the Max for Live device (../../timescale/apollo_timescale.js).
import timescale from "../../timescale/apollo_timescale.js";

export const { percentToFactor, clampPercent, classifyParamName } = timescale;

// Native MIDI effects sit before the instrument; the first device that isn't
// one of these is the instrument.
const MIDI_EFFECTS = new Set([
  "Arpeggiator", "Chord", "Note Length", "Pitch", "Random", "Scale", "Velocity",
  "CC Control", "Expression Control", "MIDI Effect Rack", "MPE Control",
  "Note Echo", "Bouncy Notes", "Microtuner", "MIDI Monitor",
]);

export function pickInstrumentIndex(deviceNames: string[]): number {
  return deviceNames.findIndex((n) => !MIDI_EFFECTS.has(n));
}

export interface ParamInfo {
  name: string;
  min: number;
  max: number;
  value: number;
  isQuantized: boolean;
}

export type Change =
  | { name: string; kind: "operator-time" | "time" | "rate"; from: number; to: number }
  | { name: string; kind: "skipped"; reason: string };

// Operator's global Time knob: a linear -100%..+100% control. Map knob % onto
// its internal range and add it.
function operatorTime(p: ParamInfo, percent: number): number {
  const span = p.max - p.min;
  const currentPct = ((p.value - p.min) / span) * 200 - 100;
  const nextPct = Math.max(-100, Math.min(100, currentPct + clampPercent(percent)));
  return p.min + ((nextPct + 100) / 200) * span;
}

// The SDK exposes only raw internal values (no "12 ms" display strings), so we
// can scale a parameter only when its internal value is in real units (ms / Hz),
// i.e. proportional to what you hear. Normalised 0..1 params have an unknown
// curve and are reported instead of guessed at.
function isInRealUnits(p: ParamInfo): boolean {
  return p.max > 1;
}

export function planChanges(deviceName: string, params: ParamInfo[], percent: number): Change[] {
  const k = percentToFactor(percent);
  const isOperator = deviceName === "Operator";
  const out: Change[] = [];

  for (const p of params) {
    if (p.isQuantized) continue;
    if (isOperator && p.name === "Time") {
      out.push({ name: p.name, kind: "operator-time", from: p.value, to: operatorTime(p, percent) });
      continue;
    }
    const kind = classifyParamName(p.name);
    if (!kind) continue;
    // Operator envelopes are already covered by its Time knob.
    if (isOperator && kind === "time") continue;
    if (!isInRealUnits(p)) {
      out.push({ name: p.name, kind: "skipped", reason: "normalised 0..1 value, curve unknown" });
      continue;
    }
    const raw = kind === "time" ? p.value * k : p.value / k;
    out.push({ name: p.name, kind, from: p.value, to: Math.max(p.min, Math.min(p.max, raw)) });
  }
  return out;
}

// Ranges to clear on the duplicate so it keeps only [start, end).
export function outsideRanges(start: number, end: number, lastClipEnd: number): Array<[number, number]> {
  const out: Array<[number, number]> = [];
  if (start > 0) out.push([0, start]);
  if (lastClipEnd > end) out.push([end, lastClipEnd]);
  return out;
}

// Dialog posts `{"percent": n}` on Apply and "" on Cancel.
export function parseDialogResult(result: string): number | null {
  if (!result) return null;
  try {
    const p = Number(JSON.parse(result).percent);
    return Number.isFinite(p) && p !== 0 ? clampPercent(p) : null;
  } catch {
    return null;
  }
}

export function formatPercent(p: number): string {
  return `${p > 0 ? "+" : ""}${p}%`;
}

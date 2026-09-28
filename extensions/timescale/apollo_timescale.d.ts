// Types for the pure helpers in apollo_timescale.js, shared with the
// Ableton Extension in ../timescale-extension.
declare const timescale: {
  percentToFactor(p: number): number;
  clampPercent(p: number): number;
  classifyParamName(name: string): "time" | "rate" | null;
  parseDisplay(str: string): { value: number; unit: "ms" | "hz" | "%" } | null;
  solveForDisplay(
    display: (raw: number) => number | null,
    min: number,
    max: number,
    target: number,
    iterations?: number,
  ): number | null;
  targetDisplay(baseDisplay: number, unit: "ms" | "hz" | "%", p: number): number;
};
export = timescale;

// How big a goals-minus-xG gap chance alone produces. Each unblocked shot
// goes in with its xG as the probability, so on a set of shots the goals
// scored vary by sum p(1 - p). Season files keep totals, not the shots, so
// the shots are taken as all having the average xG: that never
// understates the spread. With no shot count it falls back to Poisson
// (variance = xG), a touch wider again.

const Z95 = 1.96;

/** Variance of the goals scored on shots worth `xg` in all, over `n` shots. */
export const goalVar = (xg: number, n?: number) =>
  xg <= 0 ? 0 : n && n > xg ? xg * (1 - xg / n) : xg;

/** Half-width of a 95% interval from a variance. */
export const ci95 = (variance: number) => Z95 * Math.sqrt(variance);

/** Shooter GAx: goals minus ixG on his own shots. */
export const gaxCi = (ixg: number, att: number) => ci95(goalVar(ixg, att));

/** Goalie GSAx: xGA minus goals allowed on the unblocked shots he faced. */
export const gsaxCi = (xga: number, sa: number) => ci95(goalVar(xga, sa));

/** On-ice goal differential minus xG differential: chance on both ends. */
export const onIceCi = (xgf: number, xga: number) => ci95(goalVar(xgf) + goalVar(xga));

/** The gap is bigger than chance alone usually makes it. */
export const clears = (v: number | null | undefined, half: number) => v != null && Math.abs(v) > half;

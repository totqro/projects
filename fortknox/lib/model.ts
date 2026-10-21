import "server-only";
import { gameIds, rawSheet } from "./data";
import { unpack } from "./unpack";

// How the served model is doing on a season, measured from the published
// sheets themselves so the model page can't drift from the games.

export interface CalBin { lo: number; hi: number; n: number; xg: number; goals: number; rate: number; ciLo: number; ciHi: number }
export interface ModelStats { shots: number; xg: number; goals: number; auc: number; logLoss: number; bins: CalBin[] }

/** Bin edges for the calibration chart: narrow where most shots are. */
const EDGES = [0, 0.02, 0.04, 0.06, 0.08, 0.1, 0.13, 0.17, 0.22, 0.3, 0.4, 1];

/** 95% Wilson interval for k successes in n. */
function wilson(k: number, n: number) {
  if (!n) return [0, 0];
  const z = 1.96, p = k / n, d = 1 + (z * z) / n;
  const c = (p + (z * z) / (2 * n)) / d, h = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / d;
  return [Math.max(0, c - h), Math.min(1, c + h)];
}

/** Rank-based AUC (Mann-Whitney), ties at their average rank. */
function auc(rows: [number, number][]) {
  const s = rows.slice().sort((a, b) => a[0] - b[0]);
  let pos = 0, rankSum = 0;
  for (let i = 0; i < s.length;) {
    let j = i;
    while (j < s.length && s[j][0] === s[i][0]) j++;
    const avg = (i + j + 1) / 2;
    for (let k = i; k < j; k++) if (s[k][1]) { pos++; rankSum += avg; }
    i = j;
  }
  const neg = s.length - pos;
  return pos && neg ? (rankSum - (pos * (pos + 1)) / 2) / (pos * neg) : NaN;
}

/** Every unblocked shot of a season: AUC, log loss, xG against goals, and
 *  the calibration bins. */
export function modelStats(season: number): ModelStats {
  const rows: [number, number][] = [];
  for (const id of gameIds(season))
    for (const s of unpack(rawSheet(id)).shots)
      if (s.ev !== "BLOCK") rows.push([s.xg, s.ev === "GOAL" ? 1 : 0]);
  const eps = 1e-6;
  const logLoss = -rows.reduce((a, [p, y]) => {
    const q = Math.min(1 - eps, Math.max(eps, p));
    return a + (y ? Math.log(q) : Math.log(1 - q));
  }, 0) / rows.length;
  const bins = EDGES.slice(0, -1).map((lo, i) => {
    const hi = EDGES[i + 1], inBin = rows.filter(([p]) => p >= lo && (p < hi || (hi === 1 && p <= 1)));
    const goals = inBin.reduce((a, r) => a + r[1], 0), xg = inBin.reduce((a, r) => a + r[0], 0);
    const [ciLo, ciHi] = wilson(goals, inBin.length);
    return { lo, hi, n: inBin.length, xg, goals, rate: inBin.length ? goals / inBin.length : 0, ciLo, ciHi };
  }).filter(b => b.n > 0);
  return {
    shots: rows.length, xg: rows.reduce((a, r) => a + r[0], 0), goals: rows.reduce((a, r) => a + r[1], 0),
    auc: auc(rows), logLoss, bins,
  };
}

// Who deserved to win a game, from its shots. Shots at an empty net are left
// out: they pad the leading team's xG once the game is settled.
//
// Deserve to win is each team's chance of winning had the game's shots been
// taken again, each going in with its xG as the probability.
//
// The xG standings use a plainer call: the side with more xG gets the xG win
// (2 points); the other side gets a point back, like an overtime loss, when
// it finished within CLOSE of the winner.
import type { Shot } from "./types";

/** An xG margin this small or smaller counts as a close game. */
export const CLOSE = 0.25;

export interface Deserved {
  /** Expected goals with empty-net shots left out. */
  hxg: number;
  axg: number;
  /** Deserve to win: the home team's chance of winning had every one of
   *  those shots gone in with its xG as the probability. A game level on
   *  goals counts half, as a shootout coin flip. */
  hwin: number;
}

export type XgResult = "W" | "L" | "OTL";

/** The chance of scoring exactly 0, 1, 2… goals on shots worth these xG
 *  each, every shot going in or not on its own. Computed exactly, shot by
 *  shot (what a Monte Carlo over the shots estimates). */
export function goalChances(xgs: number[]): number[] {
  let d = [1];
  for (const p of xgs) {
    const n = new Array<number>(d.length + 1).fill(0);
    for (let k = 0; k < d.length; k++) { n[k] += d[k] * (1 - p); n[k + 1] += d[k] * p; }
    d = n;
  }
  return d;
}

/** The shots deserve-to-win counts for each side: unblocked, empty-net
 *  shots left out. */
export function sides(shots: Shot[], home: string) {
  const h: number[] = [], a: number[] = [];
  for (const s of shots) {
    if (s.ev === "BLOCK" || s.sit === "EN_AGAINST") continue;
    (s.team === home ? h : a).push(s.xg);
  }
  return { h, a };
}

/** The chance of each final margin, home goals minus away, from -m to +m
 *  (the ends hold everything beyond), and the home team's deserve-to-win. */
export function margins(h: number[], a: number[], m = 5) {
  const H = goalChances(h), A = goalChances(a);
  const out = new Array<number>(2 * m + 1).fill(0);
  for (let i = 0; i < H.length; i++)
    for (let j = 0; j < A.length; j++)
      out[Math.max(-m, Math.min(m, i - j)) + m] += H[i] * A[j];
  let win = 0, tie = 0;
  for (let i = 0; i < H.length; i++) {
    tie += H[i] * (A[i] ?? 0);
    for (let j = 0; j < Math.min(i, A.length); j++) win += H[i] * A[j];
  }
  return { margins: out, hwin: win + tie / 2, tie };
}

export function deserved(shots: Shot[], home: string): Deserved {
  const { h, a } = sides(shots, home);
  const sum = (v: number[]) => v.reduce((t, x) => t + x, 0);
  return { hxg: sum(h), axg: sum(a), hwin: margins(h, a, 0).hwin };
}

/** The winner's deserve-to-win, from the home team's; null without one. */
export const winnerChance = (hs: number, as: number, hwin: number | null | undefined) =>
  hwin == null || hs === as ? null : hs > as ? hwin : 1 - hwin;

/** One team's xG result. A dead-even game (it happens about never) is a
 *  close loss for both: a point each. */
export function xgResult(xgf: number, xga: number): XgResult {
  if (xgf > xga) return "W";
  return xga - xgf <= CLOSE ? "OTL" : "L";
}

export const xgPoints = (r: XgResult) => (r === "W" ? 2 : r === "OTL" ? 1 : 0);

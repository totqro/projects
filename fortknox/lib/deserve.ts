// Who deserved to win a game, from its shots. Shots at an empty net are left
// out: they pad the leading team's xG once the game is settled.
//
// Deserve to win is each team's chance of winning had the game's shots been
// taken again, each going in with its xG as the probability. Deserved points
// are what that's worth in the standings, which the xG standings add up.
import type { Shot } from "./types";

export interface Deserved {
  /** Expected goals with empty-net shots left out. */
  hxg: number;
  axg: number;
  /** Deserve to win: the home team's chance of winning had every one of
   *  those shots gone in with its xG as the probability. A game level on
   *  goals counts half, as a shootout coin flip. */
  hwin: number;
  /** The chance the shots leave it level, which goes to overtime. */
  tie: number;
}

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
  const m = margins(h, a, 0);
  return { hxg: sum(h), axg: sum(a), hwin: m.hwin, tie: m.tie };
}

/** The winner's deserve-to-win, from the home team's; null without one. */
export const winnerChance = (hs: number, as: number, hwin: number | null | undefined) =>
  hwin == null || hs === as ? null : hs > as ? hwin : 1 - hwin;

/** One team's deserved points from a game, from its deserve-to-win (ties
 *  counted half) and the chance of a tie: 2 for winning outright, 1.5 for a
 *  tie (overtime: a point, and a coin flip for the second). */
export const deservedPoints = (win: number, tie: number) => 2 * win + tie / 2;

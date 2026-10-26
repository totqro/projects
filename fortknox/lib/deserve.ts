// Who won a game on expected goals. Shots at an empty net are left out: they
// pad the leading team's xG once the game is settled. The side with more xG
// gets the xG win (2 points); the other side gets a point back, like an
// overtime loss, when it finished within CLOSE of the winner.
import type { Shot } from "./types";

/** An xG margin this small or smaller counts as a close game. */
export const CLOSE = 0.25;

export interface Deserved {
  /** Expected goals with empty-net shots left out. */
  hxg: number;
  axg: number;
}

export type XgResult = "W" | "L" | "OTL";

export function deserved(shots: Shot[], home: string): Deserved {
  let hxg = 0, axg = 0;
  for (const s of shots) {
    if (s.ev === "BLOCK" || s.sit === "EN_AGAINST") continue;
    if (s.team === home) hxg += s.xg; else axg += s.xg;
  }
  return { hxg, axg };
}

/** One team's xG result. A dead-even game (it happens about never) is a
 *  close loss for both: a point each. */
export function xgResult(xgf: number, xga: number): XgResult {
  if (xgf > xga) return "W";
  return xga - xgf <= CLOSE ? "OTL" : "L";
}

export const xgPoints = (r: XgResult) => (r === "W" ? 2 : r === "OTL" ? 1 : 0);

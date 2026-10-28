import type { CSSProperties } from "react";

// Team colours for game pages and game cards, as oklch [L, C, H]. Each team
// lists its colours in order of preference, every one lifted to read on the
// dark ice (navy and black become a lighter blue or silver). The away team
// takes the first of its colours that doesn't clash with the home team's.

type Col = [l: number, c: number, h: number];

const RED: Col = [0.66, 0.2, 27], SILVER: Col = [0.84, 0.01, 250], WHITE: Col = [0.93, 0.005, 250];
const BLUE: Col = [0.67, 0.15, 262], GOLD: Col = [0.83, 0.14, 87];

const TEAM: Record<string, Col[]> = {
  ANA: [[0.74, 0.16, 50], [0.8, 0.1, 80], SILVER],
  ARI: [[0.64, 0.17, 18], [0.84, 0.07, 80], SILVER],
  BOS: [GOLD, SILVER],
  BUF: [[0.68, 0.16, 258], GOLD, SILVER],
  CGY: [RED, [0.87, 0.16, 95], WHITE],
  CAR: [RED, SILVER],
  CHI: [[0.64, 0.21, 25], [0.82, 0.13, 80], WHITE],
  COL: [[0.62, 0.17, 8], [0.74, 0.11, 238], SILVER],
  CBJ: [[0.66, 0.13, 262], RED, SILVER],
  DAL: [[0.7, 0.14, 165], SILVER],
  DET: [[0.64, 0.21, 27], WHITE],
  EDM: [[0.73, 0.18, 50], [0.66, 0.14, 262], WHITE],
  FLA: [[0.64, 0.2, 22], [0.8, 0.1, 80], [0.66, 0.12, 262]],
  LAK: [SILVER, [0.72, 0.03, 260], WHITE],
  MIN: [[0.68, 0.13, 155], [0.85, 0.08, 85], RED],
  MTL: [[0.63, 0.21, 25], BLUE, WHITE],
  NSH: [GOLD, [0.66, 0.13, 262], WHITE],
  NJD: [[0.63, 0.21, 27], [0.84, 0.06, 90], WHITE],
  NYI: [[0.73, 0.17, 50], [0.66, 0.15, 258], WHITE],
  NYR: [BLUE, RED, WHITE],
  OTT: [[0.63, 0.21, 27], [0.8, 0.11, 80], WHITE],
  PHI: [[0.72, 0.19, 45], WHITE],
  PIT: [[0.84, 0.14, 90], SILVER],
  SJS: [[0.72, 0.11, 205], [0.74, 0.16, 50], WHITE],
  SEA: [[0.85, 0.09, 190], [0.65, 0.2, 25], WHITE],
  STL: [BLUE, GOLD, WHITE],
  TBL: [[0.66, 0.16, 258], WHITE],
  TOR: [[0.66, 0.16, 258], WHITE],
  UTA: [[0.8, 0.07, 235], WHITE],
  VAN: [[0.65, 0.14, 255], [0.72, 0.14, 160], WHITE],
  VGK: [[0.79, 0.08, 85], RED, SILVER],
  WSH: [[0.63, 0.21, 25], BLUE, WHITE],
  WPG: [[0.67, 0.12, 258], [0.76, 0.1, 238], SILVER, RED],
};

const css = ([l, c, h]: Col) => `oklch(${l} ${c} ${h})`;

/** Too close to tell apart on the shot map: near in OKLab, or a red and a
 *  green at similar lightness (the pair red-green colour blindness merges). */
function clash(x: Col, y: Col) {
  const lab = ([l, c, h]: Col) => [l, c * Math.cos(h * Math.PI / 180), c * Math.sin(h * Math.PI / 180)];
  const [p, q] = [lab(x), lab(y)];
  if (Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]) < 0.13) return true;
  const red = (k: Col) => k[1] > 0.08 && (k[2] < 60 || k[2] > 340), green = (k: Col) => k[1] > 0.08 && k[2] > 120 && k[2] < 180;
  return ((red(x) && green(y)) || (green(x) && red(y))) && Math.abs(x[0] - y[0]) < 0.1;
}

/** The two colours for a game, as CSS variables to set on its wrapper: the
 *  pair that doesn't clash and stays closest to each team's first colour.
 *  Silver and white cost extra, since goals are drawn as white rings and get
 *  lost among grey dots; on a tie the home team keeps its colour. Either team
 *  unknown leaves the site's default red and periwinkle. */
export function gameColors(away: string, home: string): CSSProperties | undefined {
  const A = TEAM[away], H = TEAM[home];
  if (!A || !H) return undefined;
  const cost = (k: Col, i: number) => i + (k[1] < 0.05 ? 2 : 0);
  let best: { cost: number; a: Col; h: Col } | null = null;
  H.forEach((h, j) => A.forEach((a, i) => {
    const c = cost(h, j) + cost(a, i);
    if (!clash(a, h) && (!best || c < best.cost)) best = { cost: c, a, h };
  }));
  const pick = best as { a: Col; h: Col } | null;
  return pick ? { "--away-c": css(pick.a), "--home-c": css(pick.h) } as CSSProperties : undefined;
}

/** A team's first colour, for the swatches in the team pickers. */
export const teamColor = (ab: string) => (TEAM[ab] ? css(TEAM[ab][0]) : undefined);

/** Each team's scoreboard block on the game page: its own colours as worn,
 *  not lifted for the ice: [background, text]. */
const BLOCK: Record<string, [string, string]> = {
  ANA: ["#F47A38", "#111111"], ARI: ["#8C2633", "#E2D6B5"], BOS: ["#111111", "#FFB81C"], BUF: ["#003087", "#FFB81C"],
  CGY: ["#C8102E", "#F1BE48"], CAR: ["#CE1126", "#FFFFFF"], CHI: ["#CF0A2C", "#FFFFFF"], COL: ["#6F263D", "#FFFFFF"],
  CBJ: ["#002654", "#FFFFFF"], DAL: ["#006847", "#FFFFFF"], DET: ["#CE1126", "#FFFFFF"], EDM: ["#041E42", "#FF4C00"],
  FLA: ["#041E42", "#FFFFFF"], LAK: ["#111111", "#C9CDD1"], MIN: ["#154734", "#EAAA00"], MTL: ["#AF1E2D", "#FFFFFF"],
  NSH: ["#FFB81C", "#041E42"], NJD: ["#CE1126", "#FFFFFF"], NYI: ["#00539B", "#FFFFFF"], NYR: ["#0038A8", "#FFFFFF"],
  OTT: ["#111111", "#E4293F"], PHI: ["#F74902", "#111111"], PIT: ["#111111", "#FCB514"], SJS: ["#006D75", "#FFFFFF"],
  SEA: ["#001628", "#99D9D9"], STL: ["#002F87", "#FCB514"], TBL: ["#002868", "#FFFFFF"], TOR: ["#00205B", "#FFFFFF"],
  UTA: ["#090909", "#6CACE4"], VAN: ["#00205B", "#FFFFFF"], VGK: ["#B4975A", "#111111"], WSH: ["#C8102E", "#FFFFFF"],
  WPG: ["#041E42", "#FFFFFF"],
};
export const teamBlock = (ab: string): { bg: string; fg: string } => {
  const [bg, fg] = BLOCK[ab] ?? ["#14213D", "#FAFAF7"];
  return { bg, fg };
};

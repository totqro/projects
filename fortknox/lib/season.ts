// Standings and team summaries, built from the games themselves so they
// always match the sheets: points, then the NHL's tiebreakers. Goals include
// the shootout winner's +1, as the league's standings do; gf_x / ga_x leave
// it out for comparisons with xG. Ported from xgcalc/web/sheets.html.
import { pct, share } from "./format";
import { xgPoints, xgResult, type XgResult } from "./deserve";
import { TEAMS } from "./teams";
import type { GameSummary, Phase, SkaterSeason, TeamSeason } from "./types";

export interface TeamGame {
  id: number;
  date: string;
  home: boolean;
  opp: string;
  gf: number;
  ga: number;
  won: boolean;
  end: string;
  res: "W" | "L" | "OTL";
  gf_x: number;
  ga_x: number;
  xgf: number;
  xga: number;
  xgf5: number;
  xga5: number;
  att: number;
  atta: number;
  sog: number;
  soga: number;
  /** Expected goals for and against with empty-net shots left out, and the
   *  result they give (lib/deserve.ts); null when the games were loaded
   *  without them (lib/data.ts seasonGames). */
  dxgf: number | null;
  dxga: number | null;
  xres: XgResult | null;
}

export const phaseType = (p: Phase) => (p === "playoff" ? 3 : 2);

export function teamGames(games: GameSummary[], ab: string, phase: Phase): TeamGame[] {
  const type = phaseType(phase);
  return games.filter(x => x.type === type && (x.home === ab || x.away === ab))
    .slice().sort((a, b) => (a.date + a.id).localeCompare(b.date + b.id))
    .map(x => {
      const home = x.home === ab, gf = home ? x.hs : x.as, ga = home ? x.as : x.hs, won = gf > ga;
      const so = x.end === "SO", dv = x.dv;
      return {
        id: x.id, date: x.date, home, opp: home ? x.away : x.home, gf, ga, won, end: x.end,
        res: won ? "W" : x.end === "REG" ? "L" : "OTL",
        gf_x: gf - (so && won ? 1 : 0), ga_x: ga - (so && !won ? 1 : 0),
        xgf: home ? x.hxg : x.axg, xga: home ? x.axg : x.hxg, xgf5: home ? x.hxg5 : x.axg5, xga5: home ? x.axg5 : x.hxg5,
        dxgf: dv ? (home ? dv.hxg : dv.axg) : null, dxga: dv ? (home ? dv.axg : dv.hxg) : null,
        xres: dv ? (home ? xgResult(dv.hxg, dv.axg) : xgResult(dv.axg, dv.hxg)) : null,
        att: home ? x.hatt : x.aatt, atta: home ? x.aatt : x.hatt, sog: home ? x.hsog : x.asog, soga: home ? x.asog : x.hsog,
      };
    });
}

export interface Summary {
  gp: number; w: number; l: number; otl: number; rw: number; row: number;
  gf: number; ga: number; gf_x: number; ga_x: number; xgf: number; xga: number; xgf5: number; xga5: number;
  pts: number; ppct: number | null; diff: number; gax: number; gsax: number;
  /** xG standings: games won on xG (xw), lost by more than the close
   *  margin (xl) or within it (xotl), and the points that gives. Null
   *  without shot data. */
  xw: number | null; xl: number | null; xotl: number | null; xpts: number | null; xppct: number | null;
}

export function summarize(games: TeamGame[]): Summary {
  const t = { gp: games.length, w: 0, l: 0, otl: 0, rw: 0, row: 0, gf: 0, ga: 0, gf_x: 0, ga_x: 0, xgf: 0, xga: 0, xgf5: 0, xga5: 0 };
  for (const g of games) {
    t[g.res === "W" ? "w" : g.res === "L" ? "l" : "otl"]++;
    if (g.won && g.end === "REG") t.rw++;
    if (g.won && g.end !== "SO") t.row++;
    t.gf += g.gf; t.ga += g.ga; t.gf_x += g.gf_x; t.ga_x += g.ga_x;
    t.xgf += g.xgf; t.xga += g.xga; t.xgf5 += g.xgf5; t.xga5 += g.xga5;
  }
  const pts = 2 * t.w + t.otl;
  const dv = games.length > 0 && games.every(g => g.xres != null);
  let xw = 0, xl = 0, xotl = 0, xpts = 0;
  if (dv) for (const g of games) {
    xpts += xgPoints(g.xres!);
    if (g.xres === "W") xw++; else if (g.xres === "L") xl++; else xotl++;
  }
  const x = dv ? { xw, xl, xotl, xpts, xppct: xpts / (2 * t.gp) } : { xw: null, xl: null, xotl: null, xpts: null, xppct: null };
  return { ...t, ...x, pts, ppct: t.gp ? pts / (2 * t.gp) : null, diff: t.gf - t.ga, gax: t.gf_x - t.xgf, gsax: t.xga - t.ga_x };
}

export type StandingRow = TeamSeason & Summary & { lg: number };

/** The NHL's order: points, then points %, then its tiebreakers. */
const byPoints = (a: Summary, b: Summary) =>
  b.pts - a.pts || (b.ppct ?? 0) - (a.ppct ?? 0) || b.rw - a.rw || b.row - a.row || b.w - a.w || b.diff - a.diff;

export function standings(teams: TeamSeason[], games: GameSummary[], phase: Phase): StandingRow[] {
  return teams.map(m => ({ ...m, ...summarize(teamGames(games, m.team, phase)), team: m.team }))
    .sort(byPoints).map((t, i) => ({ ...t, lg: i + 1 }));
}

/** The same teams ranked by xG points (then xG points %, xG wins and xG
 *  share), as the real table ranks by points. `lg` becomes the xG rank; `ptsRank` keeps the real one. */
export function xgStandings(rows: StandingRow[]): (StandingRow & { ptsRank: number })[] {
  const xs = (t: StandingRow) => share(t.xgf, t.xga) ?? 0;
  return rows.map(t => ({ ...t, ptsRank: t.lg }))
    .sort((a, b) => (b.xpts ?? 0) - (a.xpts ?? 0) || (b.xppct ?? 0) - (a.xppct ?? 0) || (b.xw ?? 0) - (a.xw ?? 0) || xs(b) - xs(a))
    .map((t, i) => ({ ...t, lg: i + 1 }));
}

export type Grouping = "league" | "conference" | "division" | "wildcard";
export interface Group { title: string | null; rows: (StandingRow & { rk: string; cut?: boolean })[] }

/** The groupings the NHL publishes: league, conference, division and the
 *  wild-card view (top three in each division, then two wild cards). */
export function groupTeams(rows: StandingRow[], group: Grouping): Group[] {
  const conf = (t: StandingRow) => TEAMS[t.team]?.[1] ?? "Other";
  const div = (t: StandingRow) => TEAMS[t.team]?.[2] ?? "Other";
  const ranked = (list: StandingRow[]) => list.map((t, i) => ({ ...t, rk: String(i + 1) }));
  if (group === "league") return [{ title: null, rows: ranked(rows) }];
  if (group === "conference")
    return (["East", "West"] as const).map(c => ({ title: `${c}ern Conference`, rows: ranked(rows.filter(t => conf(t) === c)) }));
  if (group === "division")
    return ["Atlantic", "Metropolitan", "Central", "Pacific"].map(d => ({ title: `${d} Division`, rows: ranked(rows.filter(t => div(t) === d)) }));
  const out: Group[] = [];
  for (const [c, divs] of [["East", ["Atlantic", "Metropolitan"]], ["West", ["Central", "Pacific"]]] as const) {
    const leaders: StandingRow[] = [];
    for (const d of divs) {
      const top = ranked(rows.filter(t => div(t) === d).slice(0, 3));
      leaders.push(...top);
      out.push({ title: `${d} Division`, rows: top });
    }
    const rest = rows.filter(t => conf(t) === c && !leaders.some(l => l.team === t.team))
      .map((t, i) => ({ ...t, rk: i < 2 ? `WC${i + 1}` : String(i + 1), cut: i === 1 }));
    out.push({ title: `${c}ern Conference wild card`, rows: rest });
  }
  return out;
}

/* ---------- team lenses ---------- */
/* Each lens plots two numbers for every team and splits the field into four
   quadrants at the league average (or 50% / zero where that's the natural
   line). q keys: x side then y side, h = the better side. */
export type Quad = "hh" | "lh" | "hl" | "ll";
export interface Lens {
  name: string;
  desc: string;
  x: (t: StandingRow) => number | null;
  y: (t: StandingRow) => number | null;
  /** Where the quadrants split, and what to call that line; the league
   *  average when not given. */
  mx?: number;
  my?: number;
  mxl?: string;
  myl?: string;
  flipX?: boolean;
  flipY?: boolean;
  diag?: boolean;
  fx: (v: number) => string;
  fy: (v: number) => string;
  /** Axis titles, with units, and the short names the hover card uses. */
  xl: string;
  yl: string;
  xs: string;
  ys: string;
  /** How the axis ticks print: plain numbers, percentages, or signed. */
  tx: "num" | "pct";
  ty: "num" | "pct" | "signed";
  /** Sign of the x number, sign of the y number, what that means. */
  q: Record<Quad, [x: string, y: string, verdict: string]>;
}

const sgn = (v: number) => (v > 0 ? "+" : "") + v.toFixed(1);

export const LENSES: Record<string, Lens> = {
  drive: {
    name: "Chances",
    desc: "Expected goals for and against per 60 minutes at 5-on-5. The best single measure of which teams control play.",
    x: t => t["5v5"].xgf60, y: t => t["5v5"].xga60, flipY: true, fx: v => v.toFixed(2), fy: v => v.toFixed(2),
    xl: "Expected goals for per 60 min, 5v5 (xGF/60) →", yl: "Expected goals against per 60 min, 5v5 (fewer ↑)",
    xs: "5v5 xGF/60", ys: "5v5 xGA/60", tx: "num", ty: "num",
    q: { hh: ["+xGF", "−xGA", "Controlling play"], lh: ["−xGF", "−xGA", "Tight, low-event games"],
      hl: ["+xGF", "+xGA", "Wide-open games"], ll: ["−xGF", "+xGA", "Getting outplayed"] },
  },
  luck: {
    name: "Luck",
    desc: "Share of expected goals against share of real goals. Teams above the line are scoring more than their chances suggest; teams below are scoring less.",
    x: t => share(t.xgf, t.xga), y: t => share(t.gf_x, t.ga_x), mx: 0.5, my: 0.5, mxl: "Even", myl: "Even", diag: true, fx: v => pct(v), fy: v => pct(v),
    xl: "Share of expected goals (xG%) →", yl: "Share of goals (G%) ↑",
    xs: "xG%", ys: "G%", tx: "pct", ty: "pct",
    q: { hh: ["+xG%", "+G%", "Earning their results"], lh: ["−xG%", "+G%", "Results ahead of play"],
      hl: ["+xG%", "−G%", "Results behind play"], ll: ["−xG%", "−G%", "Struggling"] },
  },
  finish: {
    name: "Finishing",
    desc: "Expected goals per game against goals scored above or below expected. Finishing runs hot and cold over a season.",
    x: t => (t.gp ? t.xgf / t.gp : null), y: t => t.gax, my: 0, myl: "As expected", fx: v => v.toFixed(2), fy: sgn,
    xl: "Expected goals for per game (xGF) →", yl: "Goals above expected, season (GAx) ↑",
    xs: "xGF per game", ys: "GAx", tx: "num", ty: "signed",
    q: { hh: ["+xGF", "+GAx", "Finishing well"], lh: ["−xGF", "+GAx", "Few chances, but scoring"],
      hl: ["+xGF", "−GAx", "Missing their chances"], ll: ["−xGF", "−GAx", "Struggling to score"] },
  },
  save: {
    name: "Goaltending",
    desc: "Expected goals allowed per game against goals saved above expected. Right means fewer chances allowed; up means the goalies are stopping more than an average goalie would.",
    x: t => (t.gp ? t.xga / t.gp : null), flipX: true, y: t => t.gsax, my: 0, myl: "As expected", fx: v => v.toFixed(2), fy: sgn,
    xl: "Expected goals against per game (xGA, fewer →)", yl: "Goals saved above expected, season (GSAx) ↑",
    xs: "xGA per game", ys: "GSAx", tx: "num", ty: "signed",
    q: { hh: ["−xGA", "+GSAx", "Performing well"], lh: ["+xGA", "+GSAx", "Goalie bailing them out"],
      hl: ["−xGA", "−GSAx", "Goalie letting them down"], ll: ["+xGA", "−GSAx", "Struggling in their end"] },
  },
};
/** Which quadrant each team falls in on a lens, split the way the chart
 *  splits it (components/charts/lens.tsx). */
export function lensQuads(rows: StandingRow[], key: string): Map<string, Quad> {
  const L = LENSES[key];
  const pts = rows.map(t => ({ t, x: L.x(t), y: L.y(t) }))
    .filter((p): p is { t: StandingRow; x: number; y: number } => p.x != null && p.y != null && isFinite(p.x) && isFinite(p.y));
  const out = new Map<string, Quad>();
  if (!pts.length) return out;
  const avg = (a: number[]) => a.reduce((s, v) => s + v, 0) / a.length;
  const mx = L.mx ?? avg(pts.map(p => p.x)), my = L.my ?? avg(pts.map(p => p.y));
  for (const p of pts) {
    const hx = L.flipX ? p.x < mx : p.x >= mx, hy = L.flipY ? p.y < my : p.y >= my;
    out.set(p.t.team, `${hx ? "h" : "l"}${hy ? "h" : "l"}` as Quad);
  }
  return out;
}
export const QCOL: Record<Quad, string> = { hh: "var(--good)", lh: "var(--warn)", hl: "var(--home)", ll: "var(--bad)" };

/** On-ice 5v5 xG share minus his team's with him on the bench (a fraction;
 *  null for seasons published without off-ice numbers). */
export const relXg = (p: SkaterSeason) => {
  const on = share(p.xgf5, p.xga5), off = p.xgf5_off == null ? null : share(p.xgf5_off, p.xga5_off ?? 0);
  return on == null || off == null ? null : on - off;
};

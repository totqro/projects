// Standings and team summaries, built from the games themselves so they
// always match the sheets: points, then the NHL's tiebreakers. Goals include
// the shootout winner's +1, as the league's standings do; gf_x / ga_x leave
// it out for comparisons with xG. Ported from xgcalc/web/sheets.html.
import { pct, share } from "./format";
import { TEAMS } from "./teams";
import type { GameSummary, Phase, TeamSeason } from "./types";

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
}

export const phaseType = (p: Phase) => (p === "playoff" ? 3 : 2);

export function teamGames(games: GameSummary[], ab: string, phase: Phase): TeamGame[] {
  const type = phaseType(phase);
  return games.filter(x => x.type === type && (x.home === ab || x.away === ab))
    .slice().sort((a, b) => (a.date + a.id).localeCompare(b.date + b.id))
    .map(x => {
      const home = x.home === ab, gf = home ? x.hs : x.as, ga = home ? x.as : x.hs, won = gf > ga;
      const so = x.end === "SO";
      return {
        id: x.id, date: x.date, home, opp: home ? x.away : x.home, gf, ga, won, end: x.end,
        res: won ? "W" : x.end === "REG" ? "L" : "OTL",
        gf_x: gf - (so && won ? 1 : 0), ga_x: ga - (so && !won ? 1 : 0),
        xgf: home ? x.hxg : x.axg, xga: home ? x.axg : x.hxg, xgf5: home ? x.hxg5 : x.axg5, xga5: home ? x.axg5 : x.hxg5,
        att: home ? x.hatt : x.aatt, atta: home ? x.aatt : x.hatt, sog: home ? x.hsog : x.asog, soga: home ? x.asog : x.hsog,
      };
    });
}

export interface Summary {
  gp: number; w: number; l: number; otl: number; rw: number; row: number;
  gf: number; ga: number; gf_x: number; ga_x: number; xgf: number; xga: number; xgf5: number; xga5: number;
  pts: number; ppct: number | null; diff: number; gax: number; gsax: number;
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
  return { ...t, pts, ppct: t.gp ? pts / (2 * t.gp) : null, diff: t.gf - t.ga, gax: t.gf_x - t.xgf, gsax: t.xga - t.ga_x };
}

export type StandingRow = TeamSeason & Summary & { lg: number };

const stdCompare = (a: Summary, b: Summary) =>
  b.pts - a.pts || (b.ppct ?? 0) - (a.ppct ?? 0) || b.rw - a.rw || b.row - a.row || b.w - a.w || b.diff - a.diff;

export function standings(teams: TeamSeason[], games: GameSummary[], phase: Phase): StandingRow[] {
  return teams.map(m => ({ ...m, ...summarize(teamGames(games, m.team, phase)), team: m.team }))
    .sort(stdCompare).map((t, i) => ({ ...t, lg: i + 1 }));
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
/* Each lens plots one question about every team, splits the field into four
   quadrants at the league average (or 50% / zero where that's the natural
   line) and names them. q keys: x side then y side, h = the better side. */
export type Quad = "hh" | "lh" | "hl" | "ll";
export interface Lens {
  name: string;
  desc: string;
  x: (t: StandingRow) => number | null;
  y: (t: StandingRow) => number | null;
  mx?: number;
  my?: number;
  flipX?: boolean;
  flipY?: boolean;
  diag?: boolean;
  fx: (v: number) => string;
  fy: (v: number) => string;
  xl: string;
  yl: string;
  q: Record<Quad, [string, string]>;
}

const sgn = (v: number) => (v > 0 ? "+" : "") + v.toFixed(1);

export const LENSES: Record<string, Lens> = {
  drive: {
    name: "Play-driving",
    desc: "5-on-5 chances created against chances allowed, per 60 minutes. The best single read of who controls play, and the most predictive of future results.",
    x: t => t["5v5"].xgf60, y: t => t["5v5"].xga60, flipY: true, fx: v => v.toFixed(2), fy: v => v.toFixed(2),
    xl: "5v5 xGF/60: chances created →", yl: "5v5 xGA/60: fewer allowed ↑",
    q: { hh: ["Dominant", "create a lot, allow little"], lh: ["Defensive", "tight games, few chances either way"],
      hl: ["Run & gun", "trade chances"], ll: ["Outplayed", "chasing all night"] },
  },
  luck: {
    name: "Luck",
    desc: "Share of expected goals (the process) against share of actual goals (the results). Above the diagonal a team is scoring more than its chances say, from hot shooting or hot goaltending; below it, the bounces have gone the other way.",
    x: t => share(t.xgf, t.xga), y: t => share(t.gf_x, t.ga_x), mx: 0.5, my: 0.5, diag: true, fx: v => pct(v), fy: v => pct(v),
    xl: "xG share: share of chances →", yl: "Goal share ↑",
    q: { hh: ["Good & winning", "earning it"], lh: ["Riding luck", "outscoring their chances"],
      hl: ["Unlucky", "better than the record"], ll: ["Bad & losing", "the record is fair"] },
  },
  finish: {
    name: "Finishing",
    desc: "Chances created per game against goals scored above or below those chances. Finishing runs hot and cold and tends to drift back toward zero.",
    x: t => (t.gp ? t.xgf / t.gp : null), y: t => t.gax, my: 0, fx: v => v.toFixed(2), fy: sgn,
    xl: "xGF per game: chances created →", yl: "GAx: goals above expected ↑",
    q: { hh: ["Create & finish", "chances and the hands to bury them"], lh: ["Opportunistic", "few chances, cashing in"],
      hl: ["Snakebitten", "the chances are there, the goals aren't"], ll: ["Starved", "not much to finish"] },
  },
  save: {
    name: "Goaltending",
    desc: "Chances allowed per game against goals saved above expected. Right is fewer chances allowed; up is the goalies stopping more than an average one would.",
    x: t => (t.gp ? t.xga / t.gp : null), flipX: true, y: t => t.gsax, my: 0, fx: v => v.toFixed(2), fy: sgn,
    xl: "xGA per game: fewer allowed →", yl: "GSAx: goals saved above expected ↑",
    q: { hh: ["Locked down", "few chances, and the goalie stops them"], lh: ["Bailed out", "leaky, but the goalie is standing on his head"],
      hl: ["Leaky goalie", "the defence holds, the goalie doesn't"], ll: ["Sieve", "chances against and nobody stopping them"] },
  },
};
export const QCOL: Record<Quad, string> = { hh: "var(--good)", lh: "var(--warn)", hl: "var(--home)", ll: "var(--bad)" };

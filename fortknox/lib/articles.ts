import "server-only";
import { currentSeason, playersFile, seasonIndex, teamsFile } from "./data";
import { fmtDate, ordinal, pct, signed, sv } from "./format";
import { nickname, teamName } from "./teams";
import type { GameSummary, TeamSeason } from "./types";

// Articles written by templates from the published data, at build time. No
// model, no key, no extra pipeline step: each deploy rewrites them from the
// latest sheets, so every number is the site's own.
//
// Three formats. Each is a function from a season's data to an Article; the
// sentences are fixed, and which sentence a fact gets depends on the fact (a
// team out-chancing its record reads differently from one living on its
// goalie). To add a format: write a builder below and list it in FORMATS.

/** A run of text: plain words, or a link to a team, player or game. */
export type Seg = string | { team: string } | { player: number; name: string } | { game: number; text: string };
export type Block =
  | { t: "p"; segs: Seg[] }
  | { t: "h"; text: string }
  | { t: "table"; cols: string[]; rows: Seg[][][] };
export type Article = {
  slug: string;
  format: FormatKey;
  team?: string;
  title: string;
  dek: string;
  through: string;
  blocks: Block[];
};
type FormatKey = "week" | "team" | "regression";

export const FORMATS: Record<FormatKey, { name: string; about: string }> = {
  week: { name: "The Week in xG", about: "The last seven days: who won, whether the chances say they earned it, who's trending, and the games the better team lost." },
  regression: { name: "Regression Watch", about: "Teams, shooters and goalies whose results are furthest from their expected goals, and which way they're likely to move." },
  team: { name: "Team Report", about: "One team: where it ranks on points and on chances, its last 10, special teams, shooters and goalies." },
};

// ------------------------------------------------------------------ data

const LAST_N = 10;
const GOALIE_MIN_GP = 4;
const SHOOTER_MIN_IXG = 3;

type Window = { gp: number; w: number; l: number; otl: number; xgf: number; xga: number; share: number };
type Row = TeamSeason & { gshare: number; luck: number; ptsRank: number; xgRank: number; l10: Window; wk: Window; games: TeamGame[] };
type TeamGame = { id: number; date: string; opp: string; home: boolean; gf: number; ga: number; xgf: number; xga: number; res: "W" | "L" | "OTL"; end: string };

const rec = (w: { w: number; l: number; otl: number }) => `${w.w}-${w.l}-${w.otl}`;

function teamGames(games: GameSummary[], ab: string): TeamGame[] {
  return games
    .filter(g => g.home === ab || g.away === ab)
    .sort((a, b) => a.date.localeCompare(b.date) || a.id - b.id)
    .map(g => {
      const home = g.home === ab;
      const [gf, ga, xgf, xga] = home ? [g.hs, g.as, g.hxg, g.axg] : [g.as, g.hs, g.axg, g.hxg];
      return { id: g.id, date: g.date, opp: home ? g.away : g.home, home, gf, ga, xgf, xga, end: g.end,
        res: gf > ga ? "W" : g.end === "REG" ? "L" : "OTL" };
    });
}

function windowOf(gs: TeamGame[]): Window {
  const w = gs.filter(g => g.res === "W").length, otl = gs.filter(g => g.res === "OTL").length;
  const xgf = gs.reduce((s, g) => s + g.xgf, 0), xga = gs.reduce((s, g) => s + g.xga, 0);
  return { gp: gs.length, w, l: gs.length - w - otl, otl, xgf, xga, share: xgf + xga ? xgf / (xgf + xga) : 0.5 };
}

/** Everything the formats need, worked out once per season. */
const memo = new Map<number, ReturnType<typeof build>>();
function league(s: number) {
  if (!memo.has(s)) memo.set(s, build(s));
  return memo.get(s)!;
}
function build(s: number) {
  const games = seasonIndex(s).games.filter(g => g.type === 2);
  const through = games.reduce((m, g) => (g.date > m ? g.date : m), "");
  const d = new Date(through + "T12:00:00Z");
  d.setUTCDate(d.getUTCDate() - 6);
  const weekFrom = d.toISOString().slice(0, 10);
  const reg = teamsFile(s).regular;
  const rank = (key: (r: TeamSeason) => number) => {
    const order = [...reg].sort((a, b) => key(b) - key(a) || a.gp - b.gp).map(r => r.team);
    return (ab: string) => order.indexOf(ab) + 1;
  };
  const ptsRank = rank(r => r.pts), xgRank = rank(r => r.xgf_pct);
  const rows: Row[] = reg.map(r => {
    const tg = teamGames(games, r.team);
    const gshare = r.gf + r.ga ? r.gf / (r.gf + r.ga) : 0.5;
    return { ...r, gshare, luck: gshare - r.xgf_pct, ptsRank: ptsRank(r.team), xgRank: xgRank(r.team),
      l10: windowOf(tg.slice(-LAST_N)), wk: windowOf(tg.filter(g => g.date >= weekFrom)), games: tg };
  });
  const P = playersFile(s).regular;
  return { games, through, weekFrom, week: games.filter(g => g.date >= weekFrom), rows, skaters: P.skaters, goalies: P.goalies, n: reg.length };
}

// --------------------------------------------------------------- phrasing

const T = (team: string): Seg => ({ team });
const nick = (ab: string) => nickname(teamName(ab));
const pts = (x: number) => `${Math.abs(x * 100).toFixed(1)} points`;
const list = <X,>(xs: X[], f: (x: X) => Seg[]): Seg[] =>
  xs.flatMap((x, i) => [...(i === 0 ? [] : i === xs.length - 1 ? [xs.length > 2 ? ", and " : " and "] : [", "]), ...f(x)]);
const p = (...segs: Seg[]): Block => ({ t: "p", segs });

/** How a team's record and its chances line up, in a few words. */
function verdict(r: Row, n: number) {
  const top = n / 4, bottom = n - n / 4;
  if (r.ptsRank <= top && r.xgRank <= top) return { key: "real", head: "the real thing" } as const;
  if (r.xgRank - r.ptsRank >= 8) return { key: "lucky", head: "the record is ahead of the chances" } as const;
  if (r.ptsRank - r.xgRank >= 8) return { key: "unlucky", head: "better than the standings say" } as const;
  if (r.ptsRank > bottom && r.xgRank > bottom) return { key: "bad", head: "the chances agree with the record" } as const;
  return { key: "middle", head: "a middle-of-the-pack team, on both counts" } as const;
}

function upsets(week: GameSummary[]) {
  return week
    .map(g => {
      const homeWon = g.hs > g.as;
      const [w, l, wx, lx] = homeWon ? [g.home, g.away, g.hxg, g.axg] : [g.away, g.home, g.axg, g.hxg];
      return { g, w, l, wx, lx, gap: lx - wx };
    })
    .filter(u => u.gap > 0)
    .sort((a, b) => b.gap - a.gap);
}
const score = (g: GameSummary) => `${Math.max(g.hs, g.as)}-${Math.min(g.hs, g.as)}${g.end === "REG" ? "" : ` (${g.end})`}`;

// ----------------------------------------------------------------- formats

/** The Week in xG: the last seven days of games. */
function weekInXg(s: number): Article {
  const L = league(s);
  const played = L.rows.filter(r => r.wk.gp > 0);
  const byWeek = [...played].sort((a, b) => (2 * b.wk.w + b.wk.otl) - (2 * a.wk.w + a.wk.otl) || b.wk.share - a.wk.share);
  const best = byWeek[0];
  const worst = [...played].sort((a, b) => (2 * a.wk.w + a.wk.otl) - (2 * b.wk.w + b.wk.otl) || (b.wk.l + b.wk.otl) - (a.wk.l + a.wk.otl) || a.wk.share - b.wk.share)[0];
  const ups = upsets(L.week);
  const blocks: Block[] = [];

  // Lead: the best week, and whether the chances back it.
  blocks.push(p("The ", T(best.team), ` had the best week in the league, going ${rec(best.wk)} from ${fmtDate(L.weekFrom)} to ${fmtDate(L.through)}. `,
    best.wk.share >= 0.5
      ? `They earned it, too, with ${pct(best.wk.share)} of the expected goals in those games.`
      : `The chances tell a different story: they had only ${pct(best.wk.share)} of the expected goals, so the wins came from finishing and goaltending more than from controlling play.`,
    ...(ups[0] ? [` The week's biggest xG upset was `, { game: ups[0].g.id, text: `${nick(ups[0].w)} ${score(ups[0].g)} over the ${nick(ups[0].l)}` } as Seg,
      `, a win on ${ups[0].wx.toFixed(2)} xG against ${ups[0].lx.toFixed(2)}.`] : [])));
  blocks.push(p(`At the other end, the `, T(worst.team), ` went ${rec(worst.wk)}`,
    worst.wk.share >= 0.5 ? ` despite ${pct(worst.wk.share)} of the xG, a week that should have gone better.` : ` with ${pct(worst.wk.share)} of the xG, and deserved little more.`));

  // Who's really good: the xG share leaders against their place in the standings.
  const topXg = [...L.rows].sort((a, b) => a.xgRank - b.xgRank).slice(0, 5);
  const leader = [...L.rows].sort((a, b) => a.ptsRank - b.ptsRank)[0];
  blocks.push({ t: "h", text: "Who's driving play" });
  blocks.push(p("The ", T(topXg[0].team), ` lead the league with ${pct(topXg[0].xgf_pct)} of the expected goals this season, and sit ${ordinal(topXg[0].ptsRank)} on points. `,
    leader.team === topXg[0].team ? `The best team on the chances is also the best in the standings.`
      : leader.xgRank <= 8 ? [`The points leaders, the `, nick(leader.team), `, are ${ordinal(leader.xgRank)} on chances, close enough to call their start real.`].join("")
      : [`The points leaders, the `, nick(leader.team), `, are only ${ordinal(leader.xgRank)} in xG share. Their place at the top leans on finishing and goaltending.`].join("")));
  blocks.push({ t: "table", cols: ["Team", "xG%", "xG rank", "Points rank", "Record"],
    rows: topXg.map(r => [[T(r.team)], [pct(r.xgf_pct)], [ordinal(r.xgRank)], [ordinal(r.ptsRank)], [rec(r)]]) });

  // Trending: last 10 against the season.
  const move = [...L.rows].sort((a, b) => (b.l10.share - b.xgf_pct) - (a.l10.share - a.xgf_pct));
  const up = move.slice(0, 2), down = move.slice(-2).reverse();
  blocks.push({ t: "h", text: `Trending over the last ${LAST_N}` });
  blocks.push(p("The ", ...list(up, r => [T(r.team), ` (${pct(r.l10.share)}, up ${pts(r.l10.share - r.xgf_pct)} on the season)`]),
    ` have improved the most. The `, ...list(down, r => [T(r.team), ` (${pct(r.l10.share)}, down ${pts(r.l10.share - r.xgf_pct)})`]), ` have slipped the most.`));

  // In the crease.
  const gs = L.goalies.filter(g => g.gp >= GOALIE_MIN_GP).sort((a, b) => b.gsax - a.gsax);
  const g1 = gs[0], gz = gs[gs.length - 1];
  if (g1 && gz) {
    blocks.push({ t: "h", text: "In the crease" });
    blocks.push(p({ player: g1.id, name: g1.name }, ` (`, T(g1.team), `) leads all goalies at ${signed(g1.gsax)} goals saved above expected, a ${sv(g1.sv_pct)} save percentage on shots an average goalie would stop at ${sv(g1.xsv_pct)}. `,
      { player: gz.id, name: gz.name }, ` (`, T(gz.team), `) is last at ${signed(gz.gsax)}, ${sv(gz.sv_pct)} against an expected ${sv(gz.xsv_pct)}.`));
  }

  // The games the better team lost.
  if (ups.length) {
    blocks.push({ t: "h", text: "Won by the team with fewer chances" });
    blocks.push({ t: "table", cols: ["Date", "Game", "Winner xG", "Loser xG"],
      rows: ups.slice(0, 5).map(u => [[fmtDate(u.g.date)], [{ game: u.g.id, text: `${u.w} ${score(u.g)} ${u.l}` }], [u.wx.toFixed(2)], [u.lx.toFixed(2)]]) });
  }

  return { slug: "week-in-xg", format: "week", through: L.through,
    title: best.wk.share >= 0.5 ? `${nick(best.team)} go ${rec(best.wk)} and earn it` : `${nick(best.team)} go ${rec(best.wk)} on ${pct(best.wk.share)} of the xG`,
    dek: `${L.week.length} games from ${fmtDate(L.weekFrom)} to ${fmtDate(L.through)}, measured by the chances.`, blocks };
}

/** Regression Watch: results furthest from expected. */
function regressionWatch(s: number): Article {
  const L = league(s);
  const byLuck = [...L.rows].sort((a, b) => b.luck - a.luck);
  const hot = byLuck.slice(0, 3), cold = byLuck.slice(-3).reverse();
  const shooters = L.skaters.filter(x => x.ixg >= SHOOTER_MIN_IXG).sort((a, b) => b.gax - a.gax);
  const sHot = shooters.slice(0, 3), sCold = shooters.slice(-3).reverse();
  const blocks: Block[] = [];

  blocks.push(p(`Goals follow chances, but not week to week. These are the teams and players whose results are furthest from their expected goals so far. A gap like this tends to shrink: finishing and save percentage swing far more than the chances a team creates and gives up.`));

  blocks.push({ t: "h", text: "Teams running hot" });
  blocks.push(p("The ", ...list(hot, r => [T(r.team)]), ` have the biggest share of the goals relative to their share of the chances. The ${nick(hot[0].team)} have ${pct(hot[0].gshare)} of the goals in their games on ${pct(hot[0].xgf_pct)} of the xG, a gap of ${pts(hot[0].luck)}`,
    hot[0].gsax_team >= 3 ? `, much of it from goaltending (${signed(hot[0].gsax_team)} team GSAx).` : hot[0].gsax_team <= -3 ? `, and not from their goalies (${signed(hot[0].gsax_team)} team GSAx): it's the shooting.` : `, with goaltending close to average (${signed(hot[0].gsax_team)} team GSAx): it's the shooting.`));
  blocks.push({ t: "h", text: "Teams running cold" });
  blocks.push(p("The ", T(cold[0].team), ` have ${pct(cold[0].gshare)} of the goals on ${pct(cold[0].xgf_pct)} of the xG, ${pts(cold[0].luck)} short`,
    cold[0].gsax_team <= -3 ? `, mostly in net (${signed(cold[0].gsax_team)} team GSAx).` : `.`,
    ` Their record (${rec(cold[0])}) is likely to improve if the chances hold. The `, ...list(cold.slice(1), r => [T(r.team)]), ` are in the same spot.`));
  blocks.push({ t: "table", cols: ["Team", "Goal share", "xG share", "Gap", "Team GSAx"],
    rows: [...hot, ...cold].map(r => [[T(r.team)], [pct(r.gshare)], [pct(r.xgf_pct)], [signed(r.luck * 100)], [signed(r.gsax_team)]]) });

  blocks.push({ t: "h", text: "Shooters" });
  blocks.push(p({ player: sHot[0].id, name: sHot[0].name }, ` has ${sHot[0].g} goals on ${sHot[0].ixg.toFixed(1)} expected, the most above expected in the league (${signed(sHot[0].gax)}). `,
    { player: sCold[0].id, name: sCold[0].name }, ` is furthest below, ${sCold[0].g} on ${sCold[0].ixg.toFixed(1)} (${signed(sCold[0].gax)}). Good shooters do finish above expected, but rarely by this much over a full season; the cold ones are the better bet to pick up.`));
  blocks.push({ t: "table", cols: ["Player", "Team", "Goals", "ixG", "GAx"],
    rows: [...sHot, ...sCold].map(x => [[{ player: x.id, name: x.name }], [T(x.team)], [String(x.g)], [x.ixg.toFixed(1)], [signed(x.gax)]]) });

  return { slug: "regression-watch", format: "regression", through: L.through,
    title: `${nick(hot[0].team)} run hot, ${nick(cold[0].team)} run cold`,
    dek: `Who's ahead of their expected goals and who's behind, through ${fmtDate(L.through)}.`, blocks };
}

/** Team Report: one team's season so far. */
function teamReport(s: number, ab: string): Article | null {
  const L = league(s);
  const r = L.rows.find(x => x.team === ab);
  if (!r || r.gp === 0) return null;
  const v = verdict(r, L.n);
  const N = nick(ab);
  const rk = (f: (x: Row) => number, low = false) => [...L.rows].sort((a, b) => (low ? f(a) - f(b) : f(b) - f(a))).findIndex(x => x.team === ab) + 1;
  const pp = rk(x => x.pp.xgf60), pk = rk(x => x.pk.xga60, true), ev = rk(x => x["5v5"].xgf_pct);
  const sk = L.skaters.filter(x => x.team === ab).sort((a, b) => b.ixg - a.ixg);
  const gl = L.goalies.filter(x => x.team === ab).sort((a, b) => b.toi - a.toi).slice(0, 2);
  const d10 = r.l10.share - r.xgf_pct;
  const blocks: Block[] = [];

  blocks.push(p("The ", T(ab), ` are ${rec(r)} with ${r.pts} points, ${ordinal(r.ptsRank)} in the league. On the chances they're ${ordinal(r.xgRank)}, with ${pct(r.xgf_pct)} of the expected goals in their games (${pct(r["5v5"].xgf_pct)} at 5v5, ${ordinal(ev)}). `,
    { real: `Both say the same thing: this is one of the league's best teams.`,
      lucky: `The record is well ahead of the chances, so expect it to cool unless the finishing or goaltending keeps it up.`,
      unlucky: `They've played better than their record, and teams that out-chance opponents usually see the points follow.`,
      bad: `The chances back up the record; there's no bad luck to wait out here.`,
      middle: `Neither the record nor the chances set them apart yet.` }[v.key]));

  blocks.push(p(`They've scored ${r.gf} and allowed ${r.ga}, ${pct(r.gshare)} of the goals, ${Math.abs(r.luck) < 0.02 ? "right in line with their chances" : r.luck > 0 ? `${pts(r.luck)} more than their chances` : `${pts(r.luck)} less than their chances`}. `,
    `Their goalies are ${signed(r.gsax_team)} goals saved above expected as a group.`));

  blocks.push({ t: "h", text: `Last ${LAST_N}` });
  blocks.push(p(`${rec(r.l10)} on ${pct(r.l10.share)} of the xG, `,
    Math.abs(d10) < 0.02 ? `about what they've done all season.` : d10 > 0 ? `${pts(d10)} better than their season, so the trend is up.` : `${pts(d10)} worse than their season, so the trend is down.`));
  blocks.push({ t: "table", cols: ["Date", "Opponent", "Result", "xG"],
    rows: r.games.slice(-5).reverse().map(g => [[fmtDate(g.date)], [g.home ? "vs " : "at ", T(g.opp)],
      [{ game: g.id, text: `${g.res === "OTL" ? "L" : g.res} ${g.gf}-${g.ga}${g.end === "REG" ? "" : ` (${g.end})`}` }], [`${g.xgf.toFixed(2)}-${g.xga.toFixed(2)}`]]) });

  blocks.push({ t: "h", text: "Special teams" });
  blocks.push(p(`The power play creates ${r.pp.xgf60.toFixed(2)} xG per 60 minutes (${ordinal(pp)}); the penalty kill allows ${r.pk.xga60.toFixed(2)} (${ordinal(pk)}).`,
    pp <= 8 && pk <= 8 ? ` Both units are among the league's best.` : pp > 24 && pk > 24 ? ` Both units are near the bottom.` : ""));

  if (sk.length) {
    const cold = sk.slice(0, 6).find(x => x.gax <= -2);
    blocks.push({ t: "h", text: "Shooters" });
    blocks.push(p({ player: sk[0].id, name: sk[0].name }, ` leads the ${N} with ${sk[0].ixg.toFixed(1)} individual xG and has ${sk[0].g} goals. `,
      ...(cold ? [{ player: cold.id, name: cold.name } as Seg, ` is the one to watch: ${cold.g} goals on ${cold.ixg.toFixed(1)} expected (${signed(cold.gax)}), a gap that usually closes.`] : [])));
    blocks.push({ t: "table", cols: ["Player", "GP", "Goals", "ixG", "GAx"],
      rows: sk.slice(0, 5).map(x => [[{ player: x.id, name: x.name }], [String(x.gp)], [String(x.g)], [x.ixg.toFixed(1)], [signed(x.gax)]]) });
  }

  if (gl.length) {
    blocks.push({ t: "h", text: "Goalies" });
    blocks.push(p(...list(gl, g => [{ player: g.id, name: g.name }, ` is at ${signed(g.gsax)} GSAx with a ${sv(g.sv_pct)} save percentage in ${g.gp} games`]), `.`));
  }

  return { slug: `team-${ab.toLowerCase()}`, format: "team", team: ab, through: L.through,
    title: `${N}: ${v.key !== "middle" ? v.head
      : d10 >= 0.03 ? `trending up, ${pct(r.l10.share)} of the xG over the last ${LAST_N}`
      : d10 <= -0.03 ? `trending down, ${pct(r.l10.share)} of the xG over the last ${LAST_N}`
      : r.luck >= 0.04 ? `scoring ${pts(r.luck)} above their chances`
      : r.luck <= -0.04 ? `scoring ${pts(r.luck)} below their chances`
      : pp <= 5 ? `a ${ordinal(pp)}-ranked power play in a middling season`
      : v.head}`, dek: `${rec(r)}, ${ordinal(r.ptsRank)} on points and ${ordinal(r.xgRank)} on chances, through ${fmtDate(L.through)}.`, blocks };
}

// --------------------------------------------------------------- the list

/** A season's articles: the two league formats, then a report per team.
 *  Empty for a season with no regular-season games yet. */
export function articles(s: number): Article[] {
  if (!league(s).games.length) return [];
  const teams = [...league(s).rows].sort((a, b) => teamName(a.team).localeCompare(teamName(b.team)));
  return [weekInXg(s), regressionWatch(s), ...teams.map(r => teamReport(s, r.team)).filter((a): a is Article => !!a)];
}

export const currentArticles = () => articles(currentSeason());

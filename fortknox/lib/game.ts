// Reading a single game sheet: the written recap, the three stars and the
// lists the game page shows. Ported from xgcalc/web/sheets.html.
import { f2, ORD, signed, toi } from "./format";
import { nickname, SHOT_TYPE } from "./teams";
import type { GamePlayer, Sheet, SheetSide, Shot } from "./types";

export const pname = (G: Sheet, id: number | null) => G.players.find(p => p.id === id)?.name ?? "Unknown";
export const lastName = (G: Sheet, id: number | null) => {
  const n = pname(G, id);
  return n.split(" ").slice(1).join(" ") || n;
};

/** Saves and shots on goal against one goalie (misses aren't saves). */
export function saves(G: Sheet, id: number) {
  const on = G.shots.filter(s => s.goalie === id && (s.ev === "SHOT" || s.ev === "GOAL"));
  return { shots: on.length, saves: on.filter(s => s.ev === "SHOT").length };
}

const gsaxOf = (p: GamePlayer) => (p.xga_ ?? 0) - (p.ga_ ?? 0);

export interface Star { p: GamePlayer; why: string }
/** Goals, own-shot xG and on-ice xG balance for skaters; GSAx for goalies. */
export function stars(G: Sheet): Star[] {
  const sk = G.players.filter(p => p.pos !== "G" && (p.toi_all || p.att)).map(p => ({
    p, v: (p.g ?? 0) * 0.5 + (p.ixg ?? 0) + 0.4 * ((p.xgf ?? 0) - (p.xga ?? 0)),
    why: `${p.g ? p.g + "G, " : ""}${f2(p.ixg ?? 0)} ixG, on-ice xG ${f2(p.xgf ?? 0)}–${f2(p.xga ?? 0)}`,
  }));
  const gk = G.players.filter(p => p.pos === "G" && p.sa).map(p => {
    const s = saves(G, p.id);
    return { p, v: gsaxOf(p), why: `${s.saves} saves on ${s.shots} shots, ${signed(gsaxOf(p), 2)} GSAx` };
  });
  return [...sk, ...gk].sort((a, b) => b.v - a.v).slice(0, 3).map(({ p, why }) => ({ p, why }));
}

/** The 5-on-5 clause has to agree with the direction of the overall one. */
function fiveOnFive(w: SheetSide, l: SheetSide) {
  if (Math.abs(w.xg5 - l.xg5) <= 0.5) return "";
  return w.xg5 > l.xg5
    ? ` and ${f2(w.xg5)} to ${f2(l.xg5)} at five-on-five`
    : `, though the ${nickname(l.name)} had the better of five-on-five, ${f2(l.xg5)} to ${f2(w.xg5)}`;
}

/** Unblocked, non-empty-net shots, most dangerous first. */
export const bestChances = (G: Sheet, n: number) =>
  G.shots.filter(s => s.ev !== "BLOCK" && s.sit !== "EN_AGAINST").sort((a, b) => b.xg - a.xg).slice(0, n);

export function recap(G: Sheet) {
  const H = G.home, A = G.away, w = H.score > A.score ? H : A, l = w === H ? A : H;
  const margin = w.score - l.score;
  const verb = G.end === "SO" ? "win a shootout over" : G.end === "OT" ? "beat"
    : l.score === 0 ? "blank" : margin >= 3 ? "roll past" : margin === 1 ? "edge" : "beat";
  const headline = `${nickname(w.name)} ${verb} ${nickname(l.name)} ${w.score}–${l.score}${G.end === "OT" ? " in overtime" : ""}`;
  const s: string[] = [];
  if (Math.abs(w.xg - l.xg) < 0.35)
    s.push(`On chances it was close to even: ${f2(w.xg)} to ${f2(l.xg)} in expected goals${Math.abs(w.xg5 - l.xg5) > 0.5 ? `, ${f2(w.xg5)} to ${f2(l.xg5)} at five-on-five` : ""}.`);
  else if (w.xg >= l.xg)
    s.push(`The ${nickname(w.name)} earned it, out-chancing the ${nickname(l.name)} ${f2(w.xg)} to ${f2(l.xg)} in expected goals${fiveOnFive(w, l)}.`);
  else
    s.push(`The ${nickname(w.name)} won despite being out-chanced ${f2(l.xg)} to ${f2(w.xg)} in expected goals${l.att > w.att ? `, and out-attempted ${l.att} to ${w.att}` : ""}.`);
  const best = bestChances(G, 1)[0];
  if (best) {
    const how = best.ev === "GOAL" ? ", and it went in" : best.ev === "SHOT" ? `, stopped by ${pname(G, best.goalie)}` : ", and it missed";
    s.push(`The best chance was ${pname(G, best.shooter)}'s ${(SHOT_TYPE[best.type] ?? "").toLowerCase()} (${best.xg.toFixed(2)} xG) at ${toi(best.t)} of the ${ORD(best.p)}${how}.`);
  }
  const gks = G.players.filter(p => p.pos === "G" && p.sa).map(p => ({ p, gsax: gsaxOf(p) })).sort((a, b) => b.gsax - a.gsax);
  if (gks[0] && gks[0].gsax > 0.75) {
    const sv = saves(G, gks[0].p.id);
    s.push(`${gks[0].p.name} made ${sv.saves} saves on ${sv.shots} shots, ${gks[0].gsax.toFixed(1)} goals better than an average goalie would have done on the same chances.`);
  }
  return { headline, text: s.join(" ") };
}

/** Goals, shots on goal and xG by period for both teams. */
export function periods(G: Sheet) {
  const maxP = Math.max(3, ...G.shots.map(s => s.p));
  const ps = Array.from({ length: maxP }, (_, i) => i + 1);
  const agg = (team: string, f: (s: Shot) => number) => {
    const by = ps.map(p => G.shots.filter(s => s.team === team && s.p === p).reduce((a, s) => a + f(s), 0));
    return { by, total: by.reduce((a, v) => a + v, 0) };
  };
  const rows = (f: (s: Shot) => number) => [G.away.abbrev, G.home.abbrev].map(t => ({ team: t, ...agg(t, f) }));
  return {
    ps,
    goals: rows(s => (s.ev === "GOAL" ? 1 : 0)),
    shots: rows(s => (s.ev === "GOAL" || s.ev === "SHOT" ? 1 : 0)),
    xg: rows(s => s.xg),
  };
}

/** Goals in order with the running score. */
export function scoring(G: Sheet) {
  let a = 0, h = 0;
  return G.shots.filter(s => s.ev === "GOAL").map(s => {
    if (s.team === G.home.abbrev) h++; else a++;
    return { s, score: `${a}–${h}`, assists: (s.ast ?? []).map(id => lastName(G, id)) };
  });
}

import "server-only";
import fs from "node:fs";
import path from "node:path";
import type { GamePlayer, GameSummary, LinesFile, PlayersFile, RawSheet, SeasonIndex, Sheet, Shot, TeamsFile, Tonight } from "./types";
import { unpack } from "./unpack";
import type { GameRanks } from "@/components/game/detail";
import { deserved } from "./deserve";

// Build-time access to the published sheets in data/ (scripts/fetch-data.sh).
// Files are read once per build worker and kept in memory.

const ROOT = path.join(process.cwd(), "data");
const cache = new Map<string, unknown>();

function read<T>(rel: string): T {
  if (!cache.has(rel)) cache.set(rel, JSON.parse(fs.readFileSync(path.join(ROOT, rel), "utf8")));
  return cache.get(rel) as T;
}

/** Published seasons, newest first. */
export function seasons(): number[] {
  return read<{ seasons: number[] }>("seasons.json").seasons;
}
export const currentSeason = () => seasons()[0];

export const seasonIndex = (s: number) => read<SeasonIndex>(`${s}/index.json`);
/** The season's games, each with who deserved to win it from its shots. */
const withDv = new Map<number, GameSummary[]>();
export function seasonGames(s: number): GameSummary[] {
  if (!withDv.has(s)) withDv.set(s, seasonIndex(s).games.map(g => ({ ...g, dv: deserved(sheet(g.id).shots, g.home) })));
  return withDv.get(s)!;
}
/** The season's games as the box scores draw them (components/games/games-view.tsx
 *  MiniBox): the index rows with each game's deserve-to-win. */
export const boxScores = (s: number): GameSummary[] =>
  seasonGames(s).map(({ dv, ...g }) => ({ ...g, dw: dv ? Math.round(dv.hwin * 1000) / 1000 : undefined }));
export const teamsFile = (s: number) => read<TeamsFile>(`${s}/teams.json`);
export const playersFile = (s: number) => read<PlayersFile>(`${s}/players.json`);
/** Lines, pairs and WOWY; null for seasons published before lines.json existed. */
export const linesFile = (s: number) => (fs.existsSync(path.join(ROOT, `${s}/lines.json`)) ? read<LinesFile>(`${s}/lines.json`) : null);

/** Tonight's slate (scripts/fetch-tonight.mjs), or null when the fetch
 *  was skipped. */
export const tonight = () => (fs.existsSync(path.join(ROOT, "tonight.json")) ? read<Tonight>("tonight.json") : null);

/** NHL game ids start with the season's start year. */
export const seasonOfGame = (id: number | string) => +String(id).slice(0, 4);

export const rawSheet = (id: number | string) => read<RawSheet>(`${seasonOfGame(id)}/games/${id}.json`);

/** Every team-game of a season, sorted, for the game page's percentiles. */
const dists = new Map<number, { xgs: number[]; xg: number[]; sog: number[] }>();
function dist(s: number) {
  if (!dists.has(s)) {
    const d = { xgs: [] as number[], xg: [] as number[], sog: [] as number[] };
    for (const g of seasonIndex(s).games)
      for (const [xg, opp, sog] of [[g.hxg, g.axg, g.hsog], [g.axg, g.hxg, g.asog]]) {
        d.xg.push(xg); d.sog.push(sog); d.xgs.push(xg + opp ? xg / (xg + opp) : 0.5);
      }
    for (const v of Object.values(d)) v.sort((a, b) => a - b);
    dists.set(s, d);
  }
  return dists.get(s)!;
}
/** The share of sorted values below v, as a whole percentile. */
function below(sorted: number[], v: number) {
  let lo = 0, hi = sorted.length;
  while (lo < hi) { const m = (lo + hi) >> 1; if (sorted[m] < v) lo = m + 1; else hi = m; }
  return Math.round((100 * lo) / sorted.length);
}
/** Where each team's xG share, xG and shots on goal in a game rank among the
 *  season's team-games; null before a season has enough of them. */
export function gameRanks(raw: RawSheet): GameRanks | null {
  const s = seasonOfGame(raw.id);
  if (!seasons().includes(s)) return null;
  const d = dist(s);
  if (d.xg.length < 40) return null;
  const side = (me: RawSheet["home"], op: RawSheet["home"]) => {
    const xgs = me.xg + op.xg ? me.xg / (me.xg + op.xg) : 0.5;
    return {
      xgs: { value: `${(xgs * 100).toFixed(1)}%`, pct: below(d.xgs, xgs) },
      xg: { value: me.xg.toFixed(2), pct: below(d.xg, me.xg) },
      sog: { value: String(me.sog), pct: below(d.sog, me.sog) },
    };
  };
  return { away: side(raw.away, raw.home), home: side(raw.home, raw.away), teams: d.xg.length };
}

/** Tonight's games scored so far, ahead of their official sheets
 *  (pipeline/nhl_live.py); none when the deploy carried no live/ folder. */
export const liveIds = (): number[] =>
  fs.existsSync(path.join(ROOT, "live")) ? fs.readdirSync(path.join(ROOT, "live")).filter(f => f.endsWith(".json")).map(f => +f.slice(0, -5)) : [];
export const liveSheet = (id: number | string) => read<RawSheet>(`live/${id}.json`);
export const sheet = (id: number | string): Sheet => unpack(rawSheet(id));

/** Every game id published for a season. */
export const gameIds = (s: number) => seasonIndex(s).games.map(g => g.id);

export interface PlayerGame {
  id: number;
  date: string;
  type: number;
  season: number;
  team: string;
  opp: string;
  home: boolean;
  gf: number;
  ga: number;
  end: string;
  line: GamePlayer;
}

/** Every player's game-by-game lines across all published seasons, built by
 *  reading each game sheet once. Used by the player pages. */
let byPlayer: Map<number, PlayerGame[]> | null = null;
export function playerGames(): Map<number, PlayerGame[]> {
  if (byPlayer) return byPlayer;
  byPlayer = new Map();
  for (const s of seasons()) {
    for (const g of seasonIndex(s).games) {
      const raw = read<RawSheet>(`${s}/games/${g.id}.json`);
      for (const p of raw.players) {
        if (!(p.toi_all || p.att || p.sa)) continue;
        const home = p.team === g.home;
        const list = byPlayer.get(p.id) ?? [];
        list.push({
          id: g.id, date: g.date, type: g.type, season: s, team: p.team,
          opp: home ? g.away : g.home, home, gf: home ? g.hs : g.as, ga: home ? g.as : g.hs, end: g.end, line: p,
        });
        byPlayer.set(p.id, list);
      }
    }
  }
  for (const list of byPlayer.values()) list.sort((a, b) => (a.date + a.id).localeCompare(b.date + b.id));
  return byPlayer;
}

/** Every unblocked shot by shooter, with its game id, read once per build.
 *  Used by the player shot maps. */
let byShooter: Map<number, (Shot & { gid: number })[]> | null = null;
export function shotsByShooter() {
  if (byShooter) return byShooter;
  byShooter = new Map();
  for (const s of seasons())
    for (const g of seasonIndex(s).games)
      for (const shot of sheet(g.id).shots) {
        if (shot.ev === "BLOCK") continue;
        const list = byShooter.get(shot.shooter) ?? [];
        list.push({ ...shot, gid: g.id });
        byShooter.set(shot.shooter, list);
      }
  return byShooter;
}

/** The (season, team) pairs that have games, for the team pages. */
export function teamSeasons(): { season: number; team: string }[] {
  return seasons().flatMap(s => teamsFile(s).regular.map(t => ({ season: s, team: t.team })));
}

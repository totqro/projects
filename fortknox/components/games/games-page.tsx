import { boxScores, currentSeason, liveIds, liveSheet, seasonIndex, seasonOfGame, seasons, teamsFile, tonight } from "@/lib/data";
import { ORD, seasonLabel } from "@/lib/format";
import { deserved } from "@/lib/deserve";
import { unpack } from "@/lib/unpack";
import type { GameSummary, LiveInfo, RawSheet, TonightGame } from "@/lib/types";
import { GamesView } from "./games-view";
import { Intro } from "./intro";
import { HomeLead } from "./lead";
import { TonightStrip, type Box, type Form } from "./tonight";

const FIRST = 36;

export function GamesPage({ season, home = false }: { season: number; home?: boolean }) {
  const idx = seasonIndex(season), games = boxScores(season);
  // The season files are only rewritten when a game goes final, so on a game
  // night count the games scored so far too, or the stamp sits at the last
  // final horn while the live scores keep redeploying.
  const stamps = [idx.updated, ...(season === currentSeason() ? liveIds().map(id => liveSheet(id).live?.updated) : [])];
  const latest = stamps.filter((s): s is string => !!s).sort().at(-1)!;
  const updated = new Date(latest).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/Toronto" });
  const teams = teamsFile(season).regular.map(t => t.team).sort();
  // Whole nights, at least FIRST games, are pre-rendered; the rest load on demand.
  const cut = games.findIndex((g, i) => i >= FIRST && g.date !== games[i - 1].date);
  const recent = cut < 0 ? games : games.slice(0, cut);
  const dates = [...new Set(games.map(g => g.date))];
  const slate = home ? tonight() : null;
  return (
    <>
      <h1 className="sr-only">{home ? "NHL games and expected goals" : `${seasonLabel(season)} games`}</h1>
      {home && <Intro />}
      {home && <HomeLead season={season} skip={slate?.date} />}
      <GamesView season={season} recent={recent} total={games.length} dates={dates}
        hasPlayoffs={games.some(g => g.type === 3)} teams={teams} updated={`Updated ${updated} ET`}
        slate={slate?.games.length ? slate.date : undefined}
        tonightSection={slate && <Tonight date={slate.date} games={slate.games} />} />
    </>
  );
}

/** A live sheet as the feed's one-line summary of a game. */
const summary = (r: RawSheet): GameSummary => ({
  id: +r.id, date: r.date, type: r.type, home: r.home.abbrev, away: r.away.abbrev, hs: r.home.score, as: r.away.score,
  end: r.end, hxg: r.home.xg, axg: r.away.xg, hxg5: r.home.xg5, axg5: r.away.xg5, hatt: r.home.att, aatt: r.away.att,
  hsog: r.home.sog, asog: r.away.sog, shifts: !!r.live?.shifts,
});

/** A game on: "2nd 11:13", "2nd int.", "OT 3:02"; "Final" once over. */
function shortStatus(L: LiveInfo, end: string) {
  if (L.state === "final") return end === "REG" ? "Final" : `F/${end}`;
  if (L.period_type === "SO") return "Shootout";
  const p = ORD(L.period ?? 1);
  return L.intermission ? `${p} int.` : `${p} ${L.clock ?? ""}`.trim();
}

/** The Tonight section, with each team's season form and a box score for
 *  every game with shots: official from the season index, or so far from
 *  data/live. A season not published yet (opening night) shows the slate
 *  without numbers. */
function Tonight({ date, games }: { date: string; games: TonightGame[] }) {
  const s = games.length ? seasonOfGame(games[0].id) : 0;
  const form: Record<string, Form> = {};
  const boxes: Record<number, Box> = {};
  // Tonight's games get pages only in the season being published (app/game/[id]).
  const pages = s === currentSeason();
  if (seasons().includes(s)) {
    for (const t of teamsFile(s).regular) form[t.team] = { xg5: t["5v5"].xgf_pct, gsax: t.gsax_team };
    const official = new Map(boxScores(s).map(g => [g.id, g]));
    const live = new Set(liveIds());
    for (const g of games) {
      const x = official.get(g.id);
      if (x) boxes[g.id] = { x };
      else if (live.has(g.id)) {
        const r = liveSheet(g.id);
        const x = summary(r);
        if (r.live!.state === "final") x.dw = deserved(unpack(r).shots, x.home).hwin;
        boxes[g.id] = { x, live: r.live!.state === "live" ? shortStatus(r.live!, r.end) : undefined };
      }
    }
  }
  return <TonightStrip date={date} games={games} form={form} boxes={boxes} pages={pages} />;
}

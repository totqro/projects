import { seasonIndex, seasonOfGame, seasons, teamsFile, tonight } from "@/lib/data";
import { seasonLabel } from "@/lib/format";
import type { TonightGame } from "@/lib/types";
import { GamesView } from "./games-view";
import { Intro } from "./intro";
import { TonightStrip, type Form } from "./tonight";

const FIRST = 36;

export function GamesPage({ season, home = false }: { season: number; home?: boolean }) {
  const idx = seasonIndex(season), games = idx.games;
  const updated = new Date(idx.updated).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/Toronto" });
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
      {slate && <Tonight date={slate.date} games={slate.games} />}
      <GamesView season={season} recent={recent} total={games.length} dates={dates}
        hasPlayoffs={games.some(g => g.type === 3)} teams={teams} updated={`Updated ${updated} ET`} />
    </>
  );
}

/** The strip, with each team's season form and which games have sheets. A
 *  season not published yet (opening night) shows the slate without numbers. */
function Tonight({ date, games }: { date: string; games: TonightGame[] }) {
  const s = games.length ? seasonOfGame(games[0].id) : 0;
  const form: Record<string, Form> = {};
  let sheets: number[] = [];
  if (seasons().includes(s)) {
    for (const t of teamsFile(s).regular) form[t.team] = { xg5: t["5v5"].xgf_pct, gsax: t.gsax_team };
    const ids = new Set(seasonIndex(s).games.map(g => g.id));
    sheets = games.map(g => g.id).filter(id => ids.has(id));
  }
  return <TonightStrip date={date} games={games} form={form} sheets={sheets} />;
}

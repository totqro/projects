import { seasonIndex, teamsFile } from "@/lib/data";
import { seasonLabel } from "@/lib/format";
import { GamesView } from "./games-view";
import { Intro } from "./intro";

const FIRST = 36;

export function GamesPage({ season, home = false }: { season: number; home?: boolean }) {
  const idx = seasonIndex(season), games = idx.games;
  const updated = new Date(idx.updated).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/Toronto" });
  const teams = teamsFile(season).regular.map(t => t.team).sort();
  // Whole nights, at least FIRST games, are pre-rendered; the rest load on demand.
  const cut = games.findIndex((g, i) => i >= FIRST && g.date !== games[i - 1].date);
  const recent = cut < 0 ? games : games.slice(0, cut);
  const dates = [...new Set(games.map(g => g.date))];
  return (
    <>
      <h1 className="sr-only">{home ? "NHL games and expected goals" : `${seasonLabel(season)} games`}</h1>
      {home && <Intro />}
      <GamesView season={season} recent={recent} total={games.length} dates={dates}
        hasPlayoffs={games.some(g => g.type === 3)} teams={teams} updated={`Updated ${updated} ET`} />
    </>
  );
}

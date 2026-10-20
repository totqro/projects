import { seasonIndex, teamsFile } from "@/lib/data";
import { seasonLabel } from "@/lib/format";
import { GamesView } from "./games-view";

export function GamesPage({ season, home = false }: { season: number; home?: boolean }) {
  const idx = seasonIndex(season), games = idx.games;
  const updated = new Date(idx.updated).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/Toronto" });
  const teams = teamsFile(season).regular.map(t => t.team).sort();
  return (
    <>
      <h1 className="sr-only">{home ? "NHL games and expected goals" : `${seasonLabel(season)} games`}</h1>
      <GamesView games={games} teams={teams} updated={`Updated ${updated} ET`} />
    </>
  );
}

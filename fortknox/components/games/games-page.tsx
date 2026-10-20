import { seasonIndex, teamsFile } from "@/lib/data";
import { seasonLabel } from "@/lib/format";
import { GamesView } from "./games-view";
import { PageHead } from "@/components/site/page-head";

export function GamesPage({ season, home = false }: { season: number; home?: boolean }) {
  const idx = seasonIndex(season), games = idx.games;
  const updated = new Date(idx.updated).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/Toronto" });
  const teams = teamsFile(season).regular.map(t => t.team).sort();
  return (
    <>
      <PageHead
        title={home ? "Every NHL game, shot by shot" : `${seasonLabel(season)} games`}
        sub={`Expected goals for all ${games.length} games of ${seasonLabel(season)}. Updated ${updated} ET.`} />
      <GamesView games={games} teams={teams} />
    </>
  );
}

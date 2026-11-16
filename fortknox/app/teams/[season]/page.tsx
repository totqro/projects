import type { Metadata } from "next";
import { seasonGames, seasons, sheet, teamsFile } from "@/lib/data";
import { seasonLabel } from "@/lib/format";
import { standings, windowRows } from "@/lib/season";
import { TeamsView } from "@/components/teams/teams-view";

export const dynamicParams = false;
export const generateStaticParams = () => seasons().map(s => ({ season: String(s) }));

type Props = { params: Promise<{ season: string }> };

/** The recent-form windows the charts offer, in games. A window shows only
 *  once every team has played at least that many games. */
const WINDOWS = [20, 10];

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  return { title: `${seasonLabel(+(await params).season)} standings and team xG` };
}

export default async function Teams({ params }: Props) {
  const season = +(await params).season;
  const games = seasonGames(season), T = teamsFile(season);
  const regular = standings(T.regular, games, "regular");
  // 5v5 time per game and side, summed from the skaters (5 on the ice at once).
  const toi5 = new Map<number, [number, number]>();
  for (const g of games) {
    if (g.type !== 2) continue;
    const side: [number, number] = [0, 0];
    for (const p of sheet(g.id).players) if (p.pos !== "G") side[p.team === g.home ? 0 : 1] += (p.toi_5v5 ?? 0) / 5;
    toi5.set(g.id, side);
  }
  const fewest = Math.min(...regular.map(t => t.gp));
  const windows = Object.fromEntries(WINDOWS.filter(n => n <= fewest).map(n => [String(n), windowRows(regular, games, n, toi5)]));
  return (
    <>
      <h1 className="sr-only">{seasonLabel(season)} teams</h1>
      <TeamsView season={season} regular={regular} playoff={standings(T.playoff, games, "playoff")} windows={windows} />
    </>
  );
}

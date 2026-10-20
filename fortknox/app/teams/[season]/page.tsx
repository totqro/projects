import type { Metadata } from "next";
import { seasonIndex, seasons, teamsFile } from "@/lib/data";
import { seasonLabel } from "@/lib/format";
import { standings } from "@/lib/season";
import { TeamsView } from "@/components/teams/teams-view";

export const dynamicParams = false;
export const generateStaticParams = () => seasons().map(s => ({ season: String(s) }));

type Props = { params: Promise<{ season: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  return { title: `${seasonLabel(+(await params).season)} standings and team xG` };
}

export default async function Teams({ params }: Props) {
  const season = +(await params).season;
  const games = seasonIndex(season).games, T = teamsFile(season);
  return (
    <>
      <h1 className="sr-only">{seasonLabel(season)} teams</h1>
      <TeamsView season={season} regular={standings(T.regular, games, "regular")} playoff={standings(T.playoff, games, "playoff")} />
    </>
  );
}

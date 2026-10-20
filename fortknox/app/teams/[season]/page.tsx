import type { Metadata } from "next";
import { seasonIndex, seasons, teamsFile } from "@/lib/data";
import { seasonLabel } from "@/lib/format";
import { standings } from "@/lib/season";
import { PageHead } from "@/components/site/page-head";
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
      <PageHead title="Teams" sub={`${seasonLabel(season)} standings next to how each team is really playing.`} />
      <TeamsView season={season} regular={standings(T.regular, games, "regular")} playoff={standings(T.playoff, games, "playoff")} />
    </>
  );
}

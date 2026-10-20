import type { Metadata } from "next";
import { playersFile, seasons, teamsFile } from "@/lib/data";
import { seasonLabel } from "@/lib/format";
import { PlayersView } from "@/components/players/players-view";

export const dynamicParams = false;
export const generateStaticParams = () => seasons().map(s => ({ season: String(s) }));

type Props = { params: Promise<{ season: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  return { title: `${seasonLabel(+(await params).season)} skaters and goalies` };
}

export default async function Players({ params }: Props) {
  const season = +(await params).season;
  const P = playersFile(season);
  return (
    <>
      <h1 className="sr-only">{seasonLabel(season)} players</h1>
      <PlayersView season={season} data={{ regular: P.regular, playoff: P.playoff }} teams={teamsFile(season).regular.map(t => t.team).sort()} />
    </>
  );
}

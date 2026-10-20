import type { Metadata } from "next";
import { seasons } from "@/lib/data";
import { seasonLabel } from "@/lib/format";
import { GamesPage } from "@/components/games/games-page";

export const dynamicParams = false;
export const generateStaticParams = () => seasons().map(s => ({ season: String(s) }));

type Props = { params: Promise<{ season: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  return { title: `${seasonLabel(+(await params).season)} games` };
}

export default async function SeasonGames({ params }: Props) {
  return <GamesPage season={+(await params).season} />;
}

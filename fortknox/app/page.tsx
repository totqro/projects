import { currentSeason } from "@/lib/data";
import { GamesPage } from "@/components/games/games-page";

export default function Home() {
  return <GamesPage season={currentSeason()} home />;
}

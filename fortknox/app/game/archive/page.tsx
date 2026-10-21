import type { Metadata } from "next";
import { ArchivedGame } from "@/components/game/archived-game";

// One shell for every game of an older season: firebase.json rewrites their
// /game/<id> URLs here, and the page fetches the sheet and draws it.
export const metadata: Metadata = {
  title: "Game sheet",
  description: "Final score, expected goals, shot map, xG race, stars, chances, scoring and rosters for an NHL game.",
};

export default function ArchivedGamePage() {
  return <ArchivedGame />;
}

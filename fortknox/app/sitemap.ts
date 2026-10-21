import type { MetadataRoute } from "next";
import { gameIds, playerGames, seasonIndex, seasons, teamSeasons } from "@/lib/data";

export const dynamic = "force-static";

const BASE = "https://highslot.web.app";

/** Every pre-rendered page. A game's date is its last change; season pages
 *  change with the season's last game. */
export default function sitemap(): MetadataRoute.Sitemap {
  const last = (s: number) => seasonIndex(s).games[0]?.date;
  const dateOf = new Map(seasons().flatMap(s => seasonIndex(s).games.map(g => [g.id, g.date] as const)));
  const page = (path: string, lastModified?: string) => ({ url: BASE + path, ...(lastModified && { lastModified }) });
  return [
    page("/", last(seasons()[0])), page("/about"), page("/model"),
    ...seasons().flatMap(s => [`/games/${s}`, `/teams/${s}`, `/players/${s}`].map(p => page(p, last(s)))),
    ...teamSeasons().map(({ season, team }) => page(`/team/${season}/${team}`, last(season))),
    ...[...playerGames()].map(([id, log]) => page(`/player/${id}`, log[log.length - 1]?.date)),
    ...seasons().flatMap(s => gameIds(s).map(id => page(`/game/${id}`, dateOf.get(id)))),
  ];
}

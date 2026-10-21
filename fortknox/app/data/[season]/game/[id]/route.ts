import { currentSeason, gameIds, rawSheet, seasons } from "@/lib/data";

// Every game sheet of an older season as a static file, /data/<season>/game/<id>.json.
// Their game pages aren't pre-rendered; app/game/archive loads these instead.

export const dynamic = "force-static";
export const dynamicParams = false;
export const generateStaticParams = () =>
  seasons().filter(s => s !== currentSeason()).flatMap(s => gameIds(s).map(id => ({ season: String(s), id: `${id}.json` })));

export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  return Response.json(rawSheet((await params).id.replace(/\.json$/, "")));
}

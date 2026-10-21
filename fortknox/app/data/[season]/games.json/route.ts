import { seasonIndex, seasons } from "@/lib/data";

// Every game of a season as one static file. The games pages pre-render only
// the latest nights and load this when the reader filters, sorts or asks for
// more, so they don't grow with the season.

export const dynamic = "force-static";
export const generateStaticParams = () => seasons().map(s => ({ season: String(s) }));

export async function GET(_: Request, { params }: { params: Promise<{ season: string }> }) {
  return Response.json(seasonIndex(+(await params).season).games);
}

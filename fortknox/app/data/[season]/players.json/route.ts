import { playersFile, seasons } from "@/lib/data";

// A season's skater and goalie tables as one static file, for the compare
// page, which loads the season the reader picks.

export const dynamic = "force-static";
export const generateStaticParams = () => seasons().map(s => ({ season: String(s) }));

export async function GET(_: Request, { params }: { params: Promise<{ season: string }> }) {
  const { regular, playoff } = playersFile(+(await params).season);
  return Response.json({ regular, playoff });
}

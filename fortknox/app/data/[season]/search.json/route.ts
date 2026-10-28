import { playersFile, seasons } from "@/lib/data";

// Every player of a season as [id, name, team, pos], for the masthead's
// search (components/site/search.tsx), which loads it on first use.

export const dynamic = "force-static";
export const generateStaticParams = () => seasons().map(s => ({ season: String(s) }));

export async function GET(_: Request, { params }: { params: Promise<{ season: string }> }) {
  const { regular, playoff } = playersFile(+(await params).season);
  const seen = new Map<number, [number, string, string, string]>();
  for (const p of [...regular.skaters, ...regular.goalies, ...playoff.skaters, ...playoff.goalies])
    if (!seen.has(p.id)) seen.set(p.id, [p.id, p.name, p.team, p.pos]);
  return Response.json([...seen.values()]);
}

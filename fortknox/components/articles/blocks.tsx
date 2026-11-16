import Link from "next/link";
import type { Block, Seg } from "@/lib/articles";
import { teamName } from "@/lib/teams";
import { HEADING } from "@/components/site/section";

const A = "text-foreground underline decoration-border underline-offset-4 hover:decoration-foreground";

/** One run of an article's text; links go to the team, player or game page. */
function SegView({ s, season }: { s: Seg; season: number }) {
  if (typeof s === "string") return <>{s}</>;
  if ("team" in s) return <Link href={`/team/${season}/${s.team}`} className={A}>{teamName(s.team)}</Link>;
  if ("player" in s) return <Link href={`/player/${s.player}`} className={A}>{s.name}</Link>;
  return <Link href={`/game/${s.game}`} className={A}>{s.text}</Link>;
}
const Segs = ({ segs, season }: { segs: Seg[]; season: number }) => <>{segs.map((s, i) => <SegView key={i} s={s} season={season} />)}</>;

/** An article's body: paragraphs, subheads and small tables. */
export function ArticleBody({ blocks, season }: { blocks: Block[]; season: number }) {
  return (
    <div className="max-w-[72ch]">
      {blocks.map((b, i) =>
        b.t === "p" ? (
          <p key={i} className="mb-4 text-[16px] leading-relaxed text-secondary-foreground"><Segs segs={b.segs} season={season} /></p>
        ) : b.t === "h" ? (
          <h2 key={i} className={`${HEADING} mb-3 mt-8 text-[19px]`}>{b.text}</h2>
        ) : (
          <div key={i} className="mb-5 overflow-x-auto">
            <table className="w-full min-w-[420px] text-sm tabular-nums">
              <thead>
                <tr className="border-b border-border text-left text-xs uppercase tracking-[0.05em] text-muted-foreground">
                  {b.cols.map((c, j) => <th key={c} className={`py-2 pr-3 font-medium ${j ? "text-right" : ""}`}>{c}</th>)}
                </tr>
              </thead>
              <tbody>
                {b.rows.map((r, k) => (
                  <tr key={k} className="border-b border-border/60">
                    {r.map((cell, j) => <td key={j} className={`py-2 pr-3 ${j ? "text-right" : ""}`}><Segs segs={cell} season={season} /></td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ),
      )}
    </div>
  );
}

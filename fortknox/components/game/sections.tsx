import { cn } from "@/lib/utils";
import { f2, fmtDate, ORD } from "@/lib/format";
import { periods, recap, stars } from "@/lib/game";
import type { Sheet } from "@/lib/types";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Note, Tile } from "@/components/site/section";

export function Recap({ G }: { G: Sheet }) {
  const r = recap(G);
  return (
    <header className="mx-auto mb-6 max-w-3xl text-center">
      <h1 className="vault-headline font-[family-name:var(--font-display)] text-[clamp(28px,4.4vw,44px)] font-bold leading-[1.08] tracking-[-0.03em] text-balance">
        {r.headline}
      </h1>
      <p className="mt-3 text-[15px] leading-relaxed text-secondary-foreground text-pretty sm:text-base">{r.text}</p>
    </header>
  );
}

const END: Record<string, string> = { REG: "Final", OT: "Final/OT", SO: "Final/SO" };

/** The line score: both teams, the final, and four matched figures. */
export function ScoreCard({ G }: { G: Sheet }) {
  const H = G.home, A = G.away;
  const tiles: [string, string | number, string | number][] = [
    ["Expected goals", f2(A.xg), f2(H.xg)],
    ["5v5 xG", f2(A.xg5), f2(H.xg5)],
    ["Shot attempts", A.att, H.att],
    ["Shots on goal", A.sog, H.sog],
  ];
  const aWon = A.score > H.score;
  return (
    <Card className="vault-plate mb-4">
      <CardContent className="p-5">
        <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
          <div>
            <div className="font-[family-name:var(--font-display)] text-[clamp(22px,3vw,30px)] font-bold tracking-[-0.02em] text-away">{A.abbrev}</div>
            <div className="text-xs text-muted-foreground">{A.name}, away</div>
          </div>
          <div className="text-center">
            <div className="tabular font-[family-name:var(--font-display)] text-[clamp(32px,5vw,48px)] font-bold leading-none tracking-[-0.02em]">
              <span className={cn(aWon ? "vault-gold" : "text-muted-foreground")}>{A.score}</span>
              <span className="mx-2 text-muted-foreground">&ndash;</span>
              <span className={cn(!aWon ? "vault-gold" : "text-muted-foreground")}>{H.score}</span>
            </div>
            <div className="mt-1.5 text-xs text-muted-foreground">
              <span className="font-medium text-gold">{END[G.end] ?? G.end}</span>, {fmtDate(G.date)}{G.venue ? `, ${G.venue}` : ""}
            </div>
          </div>
          <div className="text-right">
            <div className="font-[family-name:var(--font-display)] text-[clamp(22px,3vw,30px)] font-bold tracking-[-0.02em] text-home">{H.abbrev}</div>
            <div className="text-xs text-muted-foreground">{H.name}, home</div>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-4">
          {tiles.map(([k, a, h]) => (
            <Tile key={k} label={k}>
              <span className="flex justify-between gap-2"><span className="text-away">{a}</span><span className="text-home">{h}</span></span>
            </Tile>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

export function Stars({ G }: { G: Sheet }) {
  return (
    <>
      <ol className="space-y-3">
        {stars(G).map(({ p, why }, i) => (
          <li key={p.id} className="flex gap-3">
            <span className={cn("vault-medal grid size-7 shrink-0 place-items-center rounded-full text-xs font-bold tabular", i === 0 ? "vault-medal-1" : i === 2 ? "vault-medal-3" : "")}>{i + 1}</span>
            <div className="min-w-0">
              <div><b className="font-semibold">{p.name}</b> <span className={p.team === G.home.abbrev ? "text-home" : "text-away"}>{p.team}</span></div>
              <div className="text-xs text-muted-foreground">{why}</div>
            </div>
          </li>
        ))}
      </ol>
      <Note className="mt-3 text-xs">Goals, own-shot xG and the xG balance while on the ice; goalies by goals saved above expected.</Note>
    </>
  );
}

export function Periods({ G }: { G: Sheet }) {
  const P = periods(G);
  const head = "h-9 px-2.5 text-xs font-medium normal-case tracking-normal text-right";
  const block = (label: string, rows: typeof P.goals, fmt: (v: number) => string | number) =>
    rows.map((r, i) => (
      <TableRow key={label + r.team} className={i === 1 ? "" : "border-b-0"}>
        {i === 0 && <TableCell rowSpan={2} className="px-2.5 py-1.5 align-middle text-xs text-muted-foreground">{label}</TableCell>}
        <TableCell className={cn("px-2.5 py-1.5", r.team === G.home.abbrev ? "text-home" : "text-away")}>{r.team}</TableCell>
        {r.by.map((v, j) => <TableCell key={j} className="px-2.5 py-1.5 text-right">{fmt(v)}</TableCell>)}
        <TableCell className="px-2.5 py-1.5 text-right font-semibold">{fmt(r.total)}</TableCell>
      </TableRow>
    ));
  return (
    <>
      <Table className="tabular text-[13px]">
        <TableHeader className="bg-transparent">
          <TableRow className="hover:bg-transparent">
            <TableHead className={cn(head, "text-left")} /><TableHead className={cn(head, "text-left")} />
            {P.ps.map(p => <TableHead key={p} className={head}>{ORD(p)}</TableHead>)}
            <TableHead className={head}>Total</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {block("Goals", P.goals, v => v)}
          {block("Shots", P.shots, v => v)}
          {block("xG", P.xg, v => v.toFixed(2))}
        </TableBody>
      </Table>
      {G.end === "SO" && <Note className="mt-2 text-xs">Decided in a shootout, which isn&apos;t in these totals.</Note>}
    </>
  );
}

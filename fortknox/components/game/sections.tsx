import Link from "next/link";
import { cn } from "@/lib/utils";
import { f2, fmtDate, ORD } from "@/lib/format";
import { liveStatus, periods, recap, saves, stars } from "@/lib/game";
import type { GamePlayer, Sheet } from "@/lib/types";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Note } from "@/components/site/section";
import { teamBlock } from "@/lib/team-colors";

/** The recap's headline, as the page's heading for screen readers; its text
 *  is the page's description (app/game/[id]/page.tsx), not drawn. */
export function Recap({ G }: { G: Sheet }) {
  return <h1 className="sr-only">{recap(G).headline}</h1>;
}

const END: Record<string, string> = { REG: "Final", OT: "Final/OT", SO: "Final/SO" };

/** One team's scoreboard block, in its own colours: abbreviation and name,
 *  and the score toward the middle. */
function TeamPlate({ ab, name, where, score, dim, href, right }: {
  ab: string; name: string; where: string; score: number; dim: boolean; href: string; right?: boolean;
}) {
  const { bg, fg } = teamBlock(ab);
  return (
    <Link href={href} style={{ background: bg, color: fg }}
      className={cn("group flex min-w-0 items-center justify-between gap-3 px-4 py-3 sm:px-6", right && "flex-row-reverse text-right")}>
      <span className="min-w-0">
        <span className="block font-[family-name:var(--font-display)] text-[clamp(30px,4vw,44px)] font-black leading-none underline-offset-4 group-hover:underline">{ab}</span>
        <span className="mt-1 block truncate text-[13px] opacity-80">{name}<span className="ml-2 text-[11px] font-semibold uppercase tracking-[0.08em]">{where}</span></span>
      </span>
      <span className={cn("tabular font-[family-name:var(--font-display)] text-[clamp(48px,7vw,72px)] font-black leading-none", dim && "opacity-45")}>{score}</span>
    </Link>
  );
}

/** The scoreboard: both teams as blocks in their colours with the score,
 *  the state between, and a strip of four matched figures under them. */
export function ScoreCard({ G }: { G: Sheet }) {
  const H = G.home, A = G.away;
  const tiles: [string, string | number, string | number][] = [
    ["Expected goals", f2(A.xg), f2(H.xg)],
    ["5v5 xG", f2(A.xg5), f2(H.xg5)],
    ["Shot attempts", A.att, H.att],
    ["Shots on goal", A.sog, H.sog],
  ];
  // Leader, while a game is on; level is neither.
  const aWon = A.score > H.score, hWon = H.score > A.score;
  const team = (ab: string) => `/team/${String(G.id).slice(0, 4)}/${ab}`;
  return (
    <header className="mb-9">
      <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-stretch">
        <TeamPlate ab={A.abbrev} name={A.name} where="away" score={A.score} dim={hWon} href={team(A.abbrev)} />
        <div className="flex flex-col items-center justify-center bg-card px-3 text-center sm:px-6">
          <span className="font-[family-name:var(--font-display)] text-lg font-extrabold uppercase tracking-[0.06em] sm:text-xl">{G.live ? liveStatus(G.live, G.end) : END[G.end] ?? G.end}</span>
          <span className="text-xs text-muted-foreground max-sm:hidden">{fmtDate(G.date)}{G.venue ? ` · ${G.venue}` : ""}</span>
        </div>
        <TeamPlate ab={H.abbrev} name={H.name} where="home" score={H.score} dim={aWon} href={team(H.abbrev)} right />
      </div>
      <dl className="grid grid-cols-2 border-b border-foreground bg-card md:grid-cols-4">
        {tiles.map(([k, a, h], i) => (
          <div key={k} className={cn("border-t border-border px-4 py-3 sm:px-6", i % 2 && "border-l", i === 2 && "md:border-l")}>
            <dt className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">{k}</dt>
            <dd className="tabular mt-1 flex items-baseline justify-between gap-2 font-[family-name:var(--font-display)] text-[28px] font-extrabold leading-none">
              <span className="text-away">{a}</span><span className="text-home">{h}</span>
            </dd>
          </div>
        ))}
      </dl>
    </header>
  );
}

/** The three stars in one row: each one's case in plain words, a line at
 *  a time, rather than a string of figures. */
export function Stars({ G }: { G: Sheet }) {
  const lines = (p: GamePlayer): string[] => {
    if (p.pos === "G") {
      const sv = saves(G, p.id), gsax = (p.xga_ ?? 0) - (p.ga_ ?? 0);
      return [`${sv.saves} saves on ${sv.shots} shots`, `${Math.abs(gsax).toFixed(1)} goals ${gsax >= 0 ? "better" : "worse"} than an average goalie on these shots`];
    }
    const g = p.g ?? 0, a = p.a ?? 0, mine = p.team, opp = mine === G.home.abbrev ? G.away.abbrev : G.home.abbrev;
    const pts = [g && `${g} ${g === 1 ? "goal" : "goals"}`, a && `${a} ${a === 1 ? "assist" : "assists"}`].filter(Boolean).join(", ");
    return [
      ...(pts ? [pts] : []),
      `${(p.ixg ?? 0).toFixed(2)} xG on his own shots`,
      `With him on the ice: ${mine} ${(p.xgf ?? 0).toFixed(2)} xG, ${opp} ${(p.xga ?? 0).toFixed(2)}`,
    ];
  };
  return (
    <ol className="grid gap-x-10 gap-y-5 sm:grid-cols-3">
      {stars(G).map(({ p }, i) => (
        <li key={p.id} className="flex gap-3">
          <span className={cn("slot-medal grid size-8 shrink-0 place-items-center rounded-full text-sm font-bold tabular", i === 0 ? "slot-medal-1" : i === 2 ? "slot-medal-3" : "")}>{i + 1}</span>
          <div className="min-w-0">
            <div className="text-[15px]">
              <Link href={`/player/${p.id}`} className="font-semibold hover:underline">{p.name}</Link>{" "}
              <span className={cn("text-xs font-semibold", p.team === G.home.abbrev ? "text-home" : "text-away")}>{p.team}</span>
            </div>
            <ul className="mt-0.5 space-y-0.5 text-[13px] text-muted-foreground">
              {lines(p).map(l => <li key={l}>{l}</li>)}
            </ul>
          </div>
        </li>
      ))}
    </ol>
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

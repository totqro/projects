"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { f1, f2, fmtDate, pct, per60, share, sv, toi, toiMin } from "@/lib/format";
import { summarize, type TeamGame } from "@/lib/season";
import { posLabel, TIPS } from "@/lib/teams";
import type { Phase } from "@/lib/types";
import { Signed, SortTable, type Column } from "@/components/tables/sortable";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { SelectField } from "@/components/site/field";
import { Note, Section, Tile } from "@/components/site/section";
import { Segmented } from "./teams-view";

/** One player's line in one of this team's games, trimmed for the page. */
export interface Line {
  gid: number; id: number; name: string; pos: string;
  toi_all: number; toi_5v5: number; g: number; a: number; ixg: number; att: number;
  xgf: number; xga: number; xgf5: number; xga5: number; sa: number; ga_: number; xga_: number;
}

interface PlayerSum extends Omit<Line, "gid"> { gp: number }

function sumLines(lines: Line[]) {
  const sk = new Map<number, PlayerSum>(), gk = new Map<number, PlayerSum>();
  const keys = ["toi_all", "toi_5v5", "g", "a", "ixg", "att", "xgf", "xga", "xgf5", "xga5", "sa", "ga_", "xga_"] as const;
  for (const p of lines) {
    const bag = p.pos === "G" ? gk : sk;
    const r = bag.get(p.id) ?? { id: p.id, name: p.name, pos: p.pos, gp: 0, toi_all: 0, toi_5v5: 0, g: 0, a: 0, ixg: 0, att: 0, xgf: 0, xga: 0, xgf5: 0, xga5: 0, sa: 0, ga_: 0, xga_: 0 };
    r.gp++;
    for (const k of keys) r[k] += p[k];
    bag.set(p.id, r);
  }
  return { skaters: [...sk.values()], goalies: [...gk.values()] };
}

const WINDOWS: [string, string, number][] = [["season", "Season", Infinity], ["20", "Last 20", 20], ["10", "Last 10", 10], ["5", "Last 5", 5]];

const link = (p: { id: number; name: string }) => <Link href={`/player/${p.id}`} className="hover:underline">{p.name}</Link>;

const SK_COLS: Column<PlayerSum>[] = [
  { k: "name", label: "Skater", l: true, get: p => p.name, asc: true, cell: link },
  { k: "pos", label: "Pos", l: true, get: p => posLabel(p.pos), asc: true, cell: p => posLabel(p.pos) },
  { k: "gp", label: "GP", get: p => p.gp, tip: "gp" },
  { k: "toi", label: "TOI/GP", get: p => p.toi_all / p.gp, cell: p => toi(p.toi_all / p.gp), tip: "toi" },
  { k: "g", label: "G", get: p => p.g, tip: "g" },
  { k: "a", label: "A", get: p => p.a, tip: "a" },
  { k: "pts", label: "P", get: p => p.g + p.a, cell: p => <b className="font-semibold">{p.g + p.a}</b>, tip: "p" },
  { k: "ixg", label: "ixG", get: p => p.ixg, cell: p => f2(p.ixg), tip: "ixg" },
  { k: "gax", label: "GAx", get: p => p.g - p.ixg, cell: p => <Signed v={p.g - p.ixg} />, tip: "gax" },
  { k: "att", label: "Att", get: p => p.att, tip: "att" },
  { k: "xgf", label: "xGF", get: p => p.xgf, cell: p => f1(p.xgf), tip: "xgf" },
  { k: "xga", label: "xGA", get: p => p.xga, cell: p => f1(p.xga), asc: true, tip: "xga" },
  { k: "xgs", label: "xG share", get: p => share(p.xgf, p.xga), cell: p => pct(share(p.xgf, p.xga)), tip: "xgs" },
  { k: "xgs5", label: "5v5 xG share", get: p => share(p.xgf5, p.xga5), cell: p => pct(share(p.xgf5, p.xga5)), tip: "xgs5" },
  { k: "xgf60", label: "5v5 xGF/60", get: p => per60(p.xgf5, p.toi_5v5), cell: p => f2(per60(p.xgf5, p.toi_5v5)), tip: "xgf60" },
  { k: "xga60", label: "5v5 xGA/60", get: p => per60(p.xga5, p.toi_5v5), cell: p => f2(per60(p.xga5, p.toi_5v5)), asc: true, tip: "xga60" },
];
const GK_COLS: Column<PlayerSum>[] = [
  { k: "name", label: "Goalie", l: true, get: p => p.name, asc: true, cell: link },
  { k: "gp", label: "GP", get: p => p.gp, tip: "gp" },
  { k: "toi", label: "Min", get: p => p.toi_all, cell: p => toiMin(p.toi_all), tip: "toitot" },
  { k: "sa", label: "Shots", get: p => p.sa, tip: "sa" },
  { k: "ga", label: "GA", get: p => p.ga_, asc: true, tip: "gaG" },
  { k: "xga", label: "xGA", get: p => p.xga_, cell: p => f1(p.xga_), tip: "xgaG" },
  { k: "gsax", label: "GSAx", get: p => p.xga_ - p.ga_, cell: p => <b className="font-semibold"><Signed v={p.xga_ - p.ga_} /></b>, tip: "gsax" },
  { k: "svp", label: "Sv%", get: p => (p.sa ? 1 - p.ga_ / p.sa : null), cell: p => sv(p.sa ? 1 - p.ga_ / p.sa : null), tip: "svp" },
  { k: "xsvp", label: "xSv%", get: p => (p.sa ? 1 - p.xga_ / p.sa : null), cell: p => sv(p.sa ? 1 - p.xga_ / p.sa : null), tip: "xsvp" },
];
const LOG_COLS: Column<TeamGame>[] = [
  { k: "date", label: "Date", l: true, get: g => g.date + g.id, cell: g => fmtDate(g.date), tip: "date" },
  { k: "opp", label: "Opp", l: true, get: g => g.opp, asc: true, cell: g => `${g.home ? "vs" : "@"} ${g.opp}`, tip: "opp" },
  { k: "res", label: "Result", l: true, get: g => g.gf - g.ga, tip: "res",
    cell: g => <><b className={cn("font-semibold", g.won ? "text-good" : "text-bad")}>{g.res}</b> {g.gf}&ndash;{g.ga}{g.end !== "REG" && <span className="text-muted-foreground"> {g.end}</span>}</> },
  { k: "xgf", label: "xGF", get: g => g.xgf, cell: g => f2(g.xgf), tip: "txgf" },
  { k: "xga", label: "xGA", get: g => g.xga, cell: g => f2(g.xga), asc: true, tip: "txga" },
  { k: "xgs", label: "xG share", get: g => share(g.xgf, g.xga), cell: g => pct(share(g.xgf, g.xga)), tip: "txgs" },
  { k: "xgs5", label: "5v5 xG share", get: g => share(g.xgf5, g.xga5), cell: g => pct(share(g.xgf5, g.xga5)), tip: "txgs5" },
  { k: "att", label: "Att", get: g => g.att, cell: g => `${g.att}–${g.atta}`, tip: "att" },
  { k: "sog", label: "SOG", get: g => g.sog, cell: g => `${g.sog}–${g.soga}`, tip: "sog" },
];

/** Expected goals for (up) and against (down) in each game, with a rolling share. */
function GameBars({ games }: { games: TeamGame[] }) {
  const router = useRouter();
  const W = 900, H = 200, L = 30, R = 10, mid = H / 2;
  const bw = Math.max(3, Math.min(18, (W - L - R) / games.length - 2));
  const max = Math.max(3, ...games.map(g => Math.max(g.xgf, g.xga)));
  const X = (i: number) => L + ((i + 0.5) * (W - L - R)) / games.length;
  const Y = (v: number) => (v / max) * (mid - 14);
  const roll = games.map((_, i) => {
    const w = games.slice(Math.max(0, i - 4), i + 1);
    return share(w.reduce((s, q) => s + q.xgf, 0), w.reduce((s, q) => s + q.xga, 0)) ?? 0.5;
  });
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Expected goals by game" className="block h-auto w-full text-[11px]">
      <line x1={L} x2={W - R} y1={mid} y2={mid} stroke="oklch(1 0 0 / 0.14)" />
      <text x={L - 6} y={mid - Y(max) + 4} textAnchor="end" fill="var(--muted-foreground)">{max.toFixed(0)}</text>
      <text x={L - 6} y={mid + Y(max) + 4} textAnchor="end" fill="var(--muted-foreground)">{max.toFixed(0)}</text>
      {games.map((g, i) => {
        const x = X(i);
        return (
          <g key={g.id} className="cursor-pointer hover:opacity-70" onClick={() => router.push(`/game/${g.id}`)}>
            <title>{`${fmtDate(g.date)} ${g.home ? "vs" : "@"} ${g.opp}: ${g.res} ${g.gf}-${g.ga}, xG ${g.xgf.toFixed(2)}-${g.xga.toFixed(2)}`}</title>
            <rect x={x - bw / 2} y={mid - Y(g.xgf)} width={bw} height={Y(g.xgf)} rx={1.5} fill="var(--home)" />
            <rect x={x - bw / 2} y={mid} width={bw} height={Y(g.xga)} rx={1.5} fill="var(--away)" opacity={0.75} />
            <rect x={x - 3} y={H - 9} width={6} height={6} rx={1} fill={g.won ? "var(--brand)" : "none"} stroke={g.won ? "var(--brand)" : "var(--muted-foreground)"} />
          </g>
        );
      })}
      {games.length > 2 && (
        <polyline fill="none" stroke="var(--foreground)" strokeWidth={1.5} opacity={0.7}
          points={roll.map((v, i) => `${X(i).toFixed(1)},${(H - 14 - v * (H - 28)).toFixed(1)}`).join(" ")} />
      )}
    </svg>
  );
}

export interface TeamData {
  season: number;
  team: string;
  name: string;
  standingLine: string | null;
  games: Record<Phase, TeamGame[]>;
  lines: Line[];
}

export function TeamView({ d }: { d: TeamData }) {
  const router = useRouter();
  const hasPlayoffs = d.games.playoff.length > 0;
  const [phase, setPhase] = React.useState<Phase>("regular");
  const [win, setWin] = React.useState("season");
  const [minGp, setMinGp] = React.useState(1);
  const all = d.games[phase];
  const n = WINDOWS.find(w => w[0] === win)![2];
  const games = all.slice(-Math.min(n, all.length));
  const t = summarize(games);
  const ids = new Set(games.map(g => g.id));
  const { skaters, goalies } = React.useMemo(() => sumLines(d.lines.filter(l => ids.has(l.gid))), [d.lines, games]); // eslint-disable-line react-hooks/exhaustive-deps
  const sk = skaters.filter(p => p.gp >= Math.min(minGp, games.length));

  const tile = (label: string, v: React.ReactNode, tip: string) => (
    <Tooltip>
      <TooltipTrigger asChild><div className="cursor-help"><Tile label={label}>{v}</Tile></div></TooltipTrigger>
      <TooltipContent className="max-w-72 leading-relaxed">{TIPS[tip]}</TooltipContent>
    </Tooltip>
  );

  if (!all.length) return <Note>No {phase === "playoff" ? "playoff " : ""}games yet.</Note>;
  return (
    <>
      <div className="mb-5 flex flex-wrap items-center gap-3">
        {hasPlayoffs && <Segmented label="Season phase" value={phase} onChange={v => { setPhase(v); setWin("season"); }} options={[["regular", "Regular season"], ["playoff", "Playoffs"]]} />}
        <Segmented label="Window" value={win} onChange={setWin}
          options={WINDOWS.filter(([, , w]) => w === Infinity || w <= all.length).map(([k, l]) => [k, l] as [string, string])} />
        <span className="text-sm text-muted-foreground">
          {games.length} game{games.length === 1 ? "" : "s"}{win !== "season" ? `, ${fmtDate(games[0].date)} to ${fmtDate(games[games.length - 1].date)}` : ""}
        </span>
      </div>

      <div className="mb-6 grid grid-cols-2 gap-2 sm:grid-cols-[repeat(auto-fit,minmax(128px,1fr))]">
        {tile("Record", `${t.w}-${t.l}-${t.otl}`, "pts")}
        {tile("Goals", `${t.gf}–${t.ga}`, "diff")}
        {tile("Expected goals", `${f1(t.xgf)}–${f1(t.xga)}`, "txgs")}
        {tile("xG share", pct(share(t.xgf, t.xga)), "txgs")}
        {tile("5v5 xG share", pct(share(t.xgf5, t.xga5)), "txgs5")}
        {tile("GAx", <Signed v={t.gax} />, "tgax")}
        {tile("GSAx", <Signed v={t.gsax} />, "tgsax")}
      </div>

      <Card className="mb-6">
        <CardHeader className="pb-2"><CardTitle>Game by game</CardTitle></CardHeader>
        <CardContent>
          <GameBars games={games} />
          <Note className="mt-2 text-xs">Expected goals for (up) and against (down) in each game. Gold squares are wins. The line is the rolling five-game xG share.</Note>
        </CardContent>
      </Card>

      <div className="space-y-8">
        <Section title="Game log">
          <SortTable rows={games} cols={LOG_COLS} initial={{ sort: "date", asc: false }} rowKey={g => g.id}
            rowProps={g => ({ className: "cursor-pointer", onClick: () => router.push(`/game/${g.id}`) })} />
        </Section>
        <Section title="Skaters" aside={
          <SelectField label="Min. games" value={minGp} onChange={v => setMinGp(+v)} className="flex-row items-center gap-2"
            options={[1, 3, 5, 10, 20].filter(m => m <= Math.max(1, games.length))} />
        }>
          <SortTable rows={sk} cols={SK_COLS} initial={{ sort: "pts", asc: false }} rowKey={p => p.id} />
        </Section>
        <Section title="Goalies">
          <SortTable rows={goalies} cols={GK_COLS} initial={{ sort: "gsax", asc: false }} rowKey={p => p.id} />
        </Section>
      </div>
      <Note className="mt-3">Player numbers are summed over the games above, for this team only. Hover a heading for what it means.</Note>
    </>
  );
}

"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { f1, f2, fmtDate, pct, per60, share, sv, toi, toiMin } from "@/lib/format";
import { summarize, type TeamGame } from "@/lib/season";
import { nickname, posLabel, teamName, TIPS } from "@/lib/teams";
import type { Phase, TeamUnits } from "@/lib/types";
import { Signed, SortTable, type Column, ShareTint } from "@/components/tables/sortable";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { SelectField } from "@/components/site/field";
import { Note, Section, Tile } from "@/components/site/section";
import { Segmented } from "./teams-view";
import { LinesTables, TeamWowy } from "./lines-view";
import { LINE_KEYS, unpackLines, type Line, type PackedLines } from "@/lib/pack";

/** A game in the log, with its 5v5 goals counted from the shot list. */
export type LogGame = TeamGame & { gf5: number; ga5: number };

interface PlayerSum extends Omit<Line, "gid"> { gp: number }

function sumLines(lines: Line[]) {
  const sk = new Map<number, PlayerSum>(), gk = new Map<number, PlayerSum>();
  const keys = LINE_KEYS;
  for (const p of lines) {
    const bag = p.pos === "G" ? gk : sk;
    const r = bag.get(p.id) ?? { id: p.id, name: p.name, pos: p.pos, gp: 0, toi_all: 0, toi_5v5: 0, g: 0, a: 0, ixg: 0, att: 0, xgf: 0, xga: 0, xgf5: 0, xga5: 0, gf: 0, ga: 0, gf5: 0, ga5: 0, sa: 0, ga_: 0, xga_: 0, sog_a: 0 };
    r.gp++;
    for (const k of keys) r[k] += p[k];
    bag.set(p.id, r);
  }
  return { skaters: [...sk.values()], goalies: [...gk.values()] };
}

const WINDOWS: [string, string, number][] = [["season", "Season", Infinity], ["20", "Last 20", 20], ["10", "Last 10", 10], ["5", "Last 5", 5]];

const link = (p: { id: number; name: string }) => <Link href={`/player/${p.id}`} className="hover:underline">{p.name}</Link>;

const SK_COLS: Column<PlayerSum>[] = [
  { k: "name", label: "Skater", l: true, pin: true, get: p => p.name, asc: true, cell: link },
  { k: "pos", label: "Pos", l: true, get: p => posLabel(p.pos), asc: true, cell: p => posLabel(p.pos) },
  { k: "gp", label: "GP", get: p => p.gp, tip: "gp" },
  { k: "toi", label: "TOI/GP", unit: "sec", get: p => p.toi_all / p.gp, cell: p => toi(p.toi_all / p.gp), tip: "toi" },
  { k: "g", label: "G", get: p => p.g, tip: "g" },
  { k: "a", label: "A", get: p => p.a, tip: "a" },
  { k: "pts", label: "P", get: p => p.g + p.a, cell: p => <b className="font-semibold">{p.g + p.a}</b>, tip: "p" },
  { k: "ixg", label: "ixG", get: p => p.ixg, cell: p => f2(p.ixg), tip: "ixg" },
  { k: "gax", label: "GAx", get: p => p.g - p.ixg, cell: p => <Signed v={p.g - p.ixg} />, tip: "gax" },
  { k: "att", label: "Att", get: p => p.att, tip: "att" },
  { k: "xgf", label: "xGF", get: p => p.xgf, cell: p => f1(p.xgf), tip: "xgf" },
  { k: "gf", label: "GF", get: p => p.gf, tip: "gfOn" },
  { k: "xga", label: "xGA", get: p => p.xga, cell: p => f1(p.xga), asc: true, tip: "xga" },
  { k: "ga", label: "GA", get: p => p.ga, asc: true, tip: "gaOn" },
  { k: "xgs", label: "xG share", get: p => share(p.xgf, p.xga), cell: p => pct(share(p.xgf, p.xga)), tip: "xgs" },
  { k: "gs", label: "G share", get: p => share(p.gf, p.ga), cell: p => pct(share(p.gf, p.ga)), tip: "gs" },
  { k: "xgs5", label: "5v5 xG share", get: p => share(p.xgf5, p.xga5), cell: p => pct(share(p.xgf5, p.xga5)), tip: "xgs5" },
  { k: "gs5", label: "5v5 G share", get: p => share(p.gf5, p.ga5), cell: p => pct(share(p.gf5, p.ga5)), tip: "gs5" },
  { k: "xgf60", label: "5v5 xGF/60", get: p => per60(p.xgf5, p.toi_5v5), cell: p => f2(per60(p.xgf5, p.toi_5v5)), tip: "xgf60" },
  { k: "gf60", label: "5v5 GF/60", get: p => per60(p.gf5, p.toi_5v5), cell: p => f2(per60(p.gf5, p.toi_5v5)), tip: "gf60" },
  { k: "xga60", label: "5v5 xGA/60", get: p => per60(p.xga5, p.toi_5v5), cell: p => f2(per60(p.xga5, p.toi_5v5)), asc: true, tip: "xga60" },
  { k: "ga60", label: "5v5 GA/60", get: p => per60(p.ga5, p.toi_5v5), cell: p => f2(per60(p.ga5, p.toi_5v5)), asc: true, tip: "ga60" },
];
const GK_COLS: Column<PlayerSum>[] = [
  { k: "name", label: "Goalie", l: true, pin: true, get: p => p.name, asc: true, cell: link },
  { k: "gp", label: "GP", get: p => p.gp, tip: "gp" },
  { k: "toi", label: "Min", unit: "sec", get: p => p.toi_all, cell: p => toiMin(p.toi_all), tip: "toitot" },
  { k: "sa", label: "Shots", get: p => p.sa, tip: "sa" },
  { k: "ga", label: "GA", get: p => p.ga_, asc: true, tip: "gaG" },
  { k: "xga", label: "xGA", get: p => p.xga_, cell: p => f1(p.xga_), tip: "xgaG" },
  { k: "gsax", label: "GSAx", get: p => p.xga_ - p.ga_, cell: p => <b className="font-semibold"><Signed v={p.xga_ - p.ga_} /></b>, tip: "gsax" },
  { k: "nsvp", label: "NHL Sv%", get: p => (p.sog_a ? 1 - p.ga_ / p.sog_a : null), cell: p => sv(p.sog_a ? 1 - p.ga_ / p.sog_a : null), tip: "nsvp" },
  { k: "svp", label: "Unbl. Sv%", get: p => (p.sa ? 1 - p.ga_ / p.sa : null), cell: p => sv(p.sa ? 1 - p.ga_ / p.sa : null), tip: "svp" },
  { k: "xsvp", label: "Unbl. xSv%", get: p => (p.sa ? 1 - p.xga_ / p.sa : null), cell: p => sv(p.sa ? 1 - p.xga_ / p.sa : null), tip: "xsvp" },
];
const LOG_COLS: Column<LogGame>[] = [
  { k: "date", label: "Date", l: true, pin: true, get: g => g.date + g.id, cell: g => fmtDate(g.date), tip: "date" },
  { k: "opp", label: "Opp", l: true, get: g => g.opp, asc: true, cell: g => `${g.home ? "vs" : "@"} ${g.opp}`, tip: "opp" },
  { k: "res", label: "Result", l: true, get: g => g.gf - g.ga, tip: "res",
    cell: g => <><b className={cn("font-semibold", g.won ? "text-good" : "text-bad")}>{g.res}</b> {g.gf}&ndash;{g.ga}{g.end !== "REG" && <span className="text-muted-foreground"> {g.end}</span>}</> },
  { k: "xgf", label: "xGF", get: g => g.xgf, cell: g => f2(g.xgf), tip: "txgf" },
  { k: "gf", label: "GF", get: g => g.gf_x, tip: "tgf" },
  { k: "xga", label: "xGA", get: g => g.xga, cell: g => f2(g.xga), asc: true, tip: "txga" },
  { k: "ga", label: "GA", get: g => g.ga_x, asc: true, tip: "tga" },
  { k: "xgs", label: "xG share", get: g => share(g.xgf, g.xga), cell: g => <ShareTint v={share(g.xgf, g.xga)} />, tip: "txgs" },
  { k: "gs", label: "G share", get: g => share(g.gf_x, g.ga_x), cell: g => pct(share(g.gf_x, g.ga_x)), tip: "tgs" },
  { k: "xgs5", label: "5v5 xG share", get: g => share(g.xgf5, g.xga5), cell: g => <ShareTint v={share(g.xgf5, g.xga5)} />, tip: "txgs5" },
  { k: "gs5", label: "5v5 G share", get: g => share(g.gf5, g.ga5), cell: g => pct(share(g.gf5, g.ga5)), tip: "tgs5" },
  { k: "att", label: "Att", get: g => g.att, cell: g => `${g.att}–${g.atta}`, tip: "att" },
  { k: "sog", label: "SOG", get: g => g.sog, cell: g => `${g.sog}–${g.soga}`, tip: "sog" },
];

/** Expected goals for (up) and against (down) in each game, with a rolling share. */
function GameBars({ games, team }: { games: TeamGame[]; team: string }) {
  const router = useRouter();
  // A hover card, not the browser's own tooltip: that one waits a second,
  // vanishes when the mouse moves, and never shows on a phone. On touch the
  // first tap on a game shows its card and a second one opens the game.
  const [hover, setHover] = React.useState<{ i: number; x: number; y: number } | null>(null);
  const touch = React.useRef(false);
  const box = React.useRef<HTMLDivElement>(null);
  // The card is pinned to the viewport, so drop it on scroll or a tap elsewhere.
  React.useEffect(() => {
    if (!hover) return;
    const off = (e: Event) => { if (e.type === "scroll" || !box.current?.contains(e.target as Node)) setHover(null); };
    addEventListener("scroll", off, { passive: true, capture: true });
    addEventListener("pointerdown", off);
    return () => { removeEventListener("scroll", off, { capture: true }); removeEventListener("pointerdown", off); };
  }, [hover]);
  const W = 900, H = 220, L = 58, R = 104, mid = H / 2;
  const bw = Math.max(3, Math.min(18, (W - L - R) / games.length - 2));
  const max = Math.ceil(Math.max(3, ...games.map(g => Math.max(g.xgf, g.xga))));
  const step = max > 6 ? 2 : 1, marks: number[] = [];
  for (let v = step; v <= max; v += step) marks.push(v);
  const X = (i: number) => L + ((i + 0.5) * (W - L - R)) / games.length;
  const Y = (v: number) => (v / max) * (mid - 14);
  const shareY = (v: number) => H - 14 - v * (H - 28);
  const roll = games.map((_, i) => {
    const w = games.slice(Math.max(0, i - 4), i + 1);
    return share(w.reduce((s, q) => s + q.xgf, 0), w.reduce((s, q) => s + q.xga, 0)) ?? 0.5;
  });
  return (
    <div ref={box} className="relative">
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Expected goals by game" className="block h-auto w-full text-[11px]"
      onPointerLeave={e => { if (e.pointerType === "mouse") setHover(null); }}>
      <line x1={L} x2={W - R} y1={mid} y2={mid} stroke="var(--grid)" />
      <text x={L - 6} y={mid + 4} textAnchor="end" fill="var(--muted-foreground)">0</text>
      {marks.flatMap(v => [mid - Y(v), mid + Y(v)].map(y => (
        <g key={`${v}${y}`}>
          <line x1={L - 3} x2={W - R} y1={y} y2={y} stroke="var(--border)" strokeDasharray="2 4" />
          <text x={L - 6} y={y + 4} textAnchor="end" fill="var(--muted-foreground)">{v}</text>
        </g>
      )))}
      <text x={12} y={mid - Y(max) / 2} transform={`rotate(-90 12 ${mid - Y(max) / 2})`} textAnchor="middle" fill="var(--home)">xG for</text>
      <text x={12} y={mid + Y(max) / 2} transform={`rotate(-90 12 ${mid + Y(max) / 2})`} textAnchor="middle" fill="var(--away)">xG against</text>
      {games.map((g, i) => {
        const x = X(i), slot = (W - L - R) / games.length;
        return (
          <g key={g.id} className={cn("cursor-pointer", hover?.i === i && "opacity-70")}
            onPointerDown={e => { touch.current = e.pointerType !== "mouse"; }}
            onPointerMove={e => { if (e.pointerType === "mouse") setHover({ i, x: e.clientX, y: e.clientY }); }}
            onPointerLeave={e => { if (e.pointerType === "mouse") setHover(null); }}
            onClick={e => {
              if (touch.current && hover?.i !== i) setHover({ i, x: e.clientX, y: e.clientY });
              else router.push(`/game/${g.id}`);
            }}>
            {/* the whole column is the target, not just the bars */}
            <rect x={x - slot / 2} y={0} width={slot} height={H} fill="transparent" />
            <rect x={x - bw / 2} y={mid - Y(g.xgf)} width={bw} height={Y(g.xgf)} rx={1.5} fill="var(--home)" />
            <rect x={x - bw / 2} y={mid} width={bw} height={Y(g.xga)} rx={1.5} fill="var(--away)" opacity={0.75} />
            <text x={x} y={H - 2} textAnchor="middle" fontSize={10} fontWeight={700}
              fill={g.res === "W" ? "var(--good)" : g.res === "L" ? "var(--bad)" : "var(--muted-foreground)"}>{g.res === "OTL" ? "OT" : g.res}</text>
          </g>
        );
      })}
      {games.length > 2 && <>
        <polyline fill="none" stroke="var(--foreground)" strokeWidth={1.75}
          points={roll.map((v, i) => `${X(i).toFixed(1)},${shareY(v).toFixed(1)}`).join(" ")} />
        {/* The line names itself at its end: no second scale to read. */}
        <text x={W - R + 10} y={shareY(roll[roll.length - 1]) - 2} fontSize={13} fontWeight={700} fill="var(--foreground)">{Math.round(roll[roll.length - 1] * 100)}%</text>
        <text x={W - R + 10} y={shareY(roll[roll.length - 1]) + 11} fontSize={10} fill="var(--muted-foreground)">xG share,</text>
        <text x={W - R + 10} y={shareY(roll[roll.length - 1]) + 23} fontSize={10} fill="var(--muted-foreground)">last 5</text>
      </>}
    </svg>
    {hover && games[hover.i] && <GameCard g={games[hover.i]} team={team} x={hover.x} y={hover.y} />}
    </div>
  );
}


function GameCard({ g, team, x, y }: { g: TeamGame; team: string; x: number; y: number }) {
  return (
    <div className="tabular pointer-events-none fixed z-50 rounded-md border border-border bg-popover px-2.5 py-2 text-xs leading-relaxed [box-shadow:var(--shadow-l)]"
      style={{ left: Math.min(x + 14, innerWidth - 200), top: y + 14 }}>
      <div className="text-muted-foreground">{fmtDate(g.date)} {g.home ? "vs" : "@"} {g.opp}</div>
      <div>
        <b className={cn("font-semibold", g.won ? "text-good" : "text-bad")}>{g.res}</b> {g.gf}&ndash;{g.ga}
        {g.end !== "REG" && <span className="text-muted-foreground"> {g.end}</span>}
      </div>
      <div className="mt-1 text-muted-foreground">Expected goals</div>
      <div><b className="font-semibold text-home">{nickname(teamName(team))} {f2(g.xgf)}</b></div>
      <div><b className="font-semibold text-away">{nickname(teamName(g.opp))} {f2(g.xga)}</b></div>
      {g.dwin != null && g.xpts != null && (
        <div className="mt-1 text-muted-foreground">
          Deserve to win: <b className={cn("font-semibold", g.dwin >= 0.5 ? "text-good" : "text-bad")}>{Math.round(g.dwin * 100)}%</b>,{" "}
          {g.xpts.toFixed(2)} deserved pts
        </div>
      )}
    </div>
  );
}

export interface TeamData {
  season: number;
  team: string;
  name: string;
  games: Record<Phase, LogGame[]>;
  lines: PackedLines;
  /** 5v5 lines, pairs and WOWY; null before lines.json existed. */
  units: Record<Phase, TeamUnits | null>;
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
  const lines = React.useMemo(() => unpackLines(d.lines), [d.lines]);
  const { skaters, goalies } = React.useMemo(() => sumLines(lines.filter(l => ids.has(l.gid))), [lines, games]); // eslint-disable-line react-hooks/exhaustive-deps
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
          <GameBars games={games} team={d.team} />
          <Note className="mt-2 text-xs">Expected goals for (up) and against (down), one bar per game, with the result under each. The line is the team&apos;s xG share over its last five games. Click a bar to open the game.</Note>
        </CardContent>
      </Card>

      <div className="space-y-8">
        <Section title="Game log">
          <SortTable rows={games} cols={LOG_COLS} initial={{ sort: "date", asc: false }} rowKey={g => g.id} csv={`${d.team}-${d.season}-games`}
            rowProps={g => ({ className: "cursor-pointer", onClick: () => router.push(`/game/${g.id}`) })} />
        </Section>
        <Section title="Skaters" aside={
          <SelectField label="Min. games" value={minGp} onChange={v => setMinGp(+v)} className="flex-row items-center gap-2"
            options={[1, 3, 5, 10, 20].filter(m => m <= Math.max(1, games.length))} />
        }>
          <SortTable rows={sk} cols={SK_COLS} initial={{ sort: "pts", asc: false }} rowKey={p => p.id} csv={`${d.team}-${d.season}-skaters`} />
        </Section>
        <Section title="Goalies">
          <SortTable rows={goalies} cols={GK_COLS} initial={{ sort: "gsax", asc: false }} rowKey={p => p.id} csv={`${d.team}-${d.season}-goalies`} />
        </Section>
      </div>
      <Note className="mt-3">Player numbers cover only the games above, for this team.</Note>
      {d.units[phase] && (
        <div className="mt-10 space-y-8">
          <p className="text-[13px] text-muted-foreground">Lines and with-or-without-you cover the whole {phase === "playoff" ? "playoffs" : "season"}, whatever window is picked above.</p>
          <LinesTables units={d.units[phase]!} csvName={`${d.team}-${d.season}`} />
          <TeamWowy units={d.units[phase]!} csvName={`${d.team}-${d.season}`} />
        </div>
      )}
    </>
  );
}

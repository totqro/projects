"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { fmtDate, share } from "@/lib/format";
import { Segmented } from "@/components/teams/teams-view";
import { Note } from "@/components/site/section";
import type { LogRow } from "./player-log";

// A player's season game by game: his own chances and goals, and how his
// team did with him on the ice, as trailing averages over the last N games.

const W = 900, L = 58, R = 92;
const n = (v?: number) => v ?? 0;
const label = (g: LogRow) => `${fmtDate(g.date)} ${g.home ? "vs" : "@"} ${g.opp}`;

/** A chart's key: one sample per mark, drawn as the chart draws it. */
type KeyItem = { label: string; kind: "line" | "dash" | "bar" | "dot"; color: string };
function Key({ items }: { items: KeyItem[] }) {
  return (
    <ul className="mb-1 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
      {items.map(i => (
        <li key={i.label} className="inline-flex items-center gap-1.5">
          <svg width="18" height="10" aria-hidden="true">
            {i.kind === "bar" ? <rect x="5" y="1" width="8" height="9" fill={i.color} opacity={0.4} />
              : i.kind === "dot" ? <circle cx="9" cy="5" r="3.5" fill={i.color} />
              : <line x1="0" x2="18" y1="5" y2="5" stroke={i.color} strokeWidth={2} strokeDasharray={i.kind === "dash" ? "4 3" : undefined} />}
          </svg>
          {i.label}
        </li>
      ))}
    </ul>
  );
}

/** A line's name and latest value at its right end, so it needs no key. */
function EndLabel({ x, y, value, name, color }: { x: number; y: number; value: string; name: string; color: string }) {
  return (
    <g fontSize={11}>
      <text x={x + 6} y={y + 4} fontWeight={700} fill={color}>{value}</text>
      <text x={x + 6} y={y + 16} fill="var(--muted-foreground)">{name}</text>
    </g>
  );
}

/** Trailing sums over the last `k` games (fewer at the start of the season). */
function trailing(rows: LogRow[], k: number, f: (g: LogRow) => number) {
  return rows.map((_, i) => rows.slice(Math.max(0, i - k + 1), i + 1).reduce((s, g) => s + f(g), 0));
}

/** Evenly spaced axis marks up to `max`. */
function marks(max: number) {
  const step = max > 6 ? 2 : max > 2 ? 1 : 0.5, out: number[] = [];
  for (let v = step; v <= max + 1e-9; v += step) out.push(v);
  return out;
}

const xAt = (count: number) => (i: number) => L + ((i + 0.5) * (W - L - R)) / count;
const barW = (count: number) => Math.max(3, Math.min(18, (W - L - R) / count - 2));
const pts = (xs: (number | null)[], X: (i: number) => number, Y: (v: number) => number) =>
  xs.flatMap((v, i) => (v == null ? [] : [`${X(i).toFixed(1)},${Y(v).toFixed(1)}`])).join(" ");

/** Shot attempts' xG per game as bars, a dot for each goal on top, and his
 *  trailing ixG and goals per game as lines. */
function Chances({ rows, k }: { rows: LogRow[]; k: number }) {
  const router = useRouter();
  const H = 190, top = 12, base = H - 22;
  const max = Math.max(1, ...rows.map(g => Math.max(n(g.line.ixg), n(g.line.g) * 0.32 + 0.2)));
  const Y = (v: number) => base - (v / max) * (base - top);
  const X = xAt(rows.length), bw = barW(rows.length);
  const ixg = trailing(rows, k, g => n(g.line.ixg)).map((s, i) => s / Math.min(k, i + 1));
  const gls = trailing(rows, k, g => n(g.line.g)).map((s, i) => s / Math.min(k, i + 1));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Individual expected goals and goals by game" className="block h-auto w-full text-[11px]">
      <line x1={L} x2={W - R} y1={base} y2={base} stroke="var(--grid)" />
      <text x={L - 6} y={base + 4} textAnchor="end" fill="var(--muted-foreground)">0</text>
      {marks(max).map(v => (
        <g key={v}>
          <line x1={L - 3} x2={W - R} y1={Y(v)} y2={Y(v)} stroke="var(--border)" strokeDasharray="2 4" />
          <text x={L - 6} y={Y(v) + 4} textAnchor="end" fill="var(--muted-foreground)">{v}</text>
        </g>
      ))}
      <text x={12} y={(base + top) / 2} transform={`rotate(-90 12 ${(base + top) / 2})`} textAnchor="middle" fill="var(--muted-foreground)">ixG per game</text>
      {rows.map((g, i) => {
        const x = X(i), v = n(g.line.ixg), goals = n(g.line.g);
        return (
          <g key={g.id} className="cursor-pointer hover:opacity-70" onClick={() => router.push(`/game/${g.id}`)}>
            <title>{`${label(g)}: ${goals} G, ${v.toFixed(2)} ixG on ${n(g.line.att)} attempts`}</title>
            <rect x={x - bw / 2} y={top} width={bw} height={base - top} fill="transparent" />
            {v > 0 && <rect x={x - bw / 2} y={Y(v)} width={bw} height={base - Y(v)} rx={1.5} fill="var(--home)" opacity={0.4} />}
            {Array.from({ length: goals }, (_, j) => (
              <circle key={j} cx={x} cy={Y(v) - 6 - j * 9} r={3.5} fill="var(--foreground)" />
            ))}
          </g>
        );
      })}
      {rows.length > 2 && <>
        <polyline fill="none" stroke="var(--home)" strokeWidth={2} points={pts(ixg, X, Y)} />
        <polyline fill="none" stroke="var(--foreground)" strokeWidth={1.5} strokeDasharray="5 4" points={pts(gls, X, Y)} />
        {(() => {
          const i = rows.length - 1, a = Y(ixg[i]), b = Y(gls[i]);
          // Keep the two labels apart when the lines end close together.
          const [ya, yb] = Math.abs(a - b) < 28 ? (a <= b ? [a - 14, a + 16] : [b + 16, b - 14]) : [a, b];
          return <>
            <EndLabel x={X(i)} y={ya} value={ixg[i].toFixed(2)} name="ixG / game" color="var(--home)" />
            <EndLabel x={X(i)} y={yb} value={gls[i].toFixed(2)} name="goals / game" color="var(--foreground)" />
          </>;
        })()}
      </>}
    </svg>
  );
}

/** His on-ice xG share and goal share over trailing windows, in all
 *  situations or at 5v5 only (where a penalty killer isn't marked down for
 *  the short-handed minutes his coach gives him). */
function OnIce({ rows, k, five }: { rows: LogRow[]; k: number; five: boolean }) {
  const H = 150, top = 10, base = H - 14;
  const Y = (v: number) => base - v * (base - top);
  const X = xAt(rows.length);
  const xf = trailing(rows, k, g => n(five ? g.line.xgf5 : g.line.xgf)), xa = trailing(rows, k, g => n(five ? g.line.xga5 : g.line.xga));
  const gf = trailing(rows, k, g => n(five ? g.line.gf5 : g.line.gf)), ga = trailing(rows, k, g => n(five ? g.line.ga5 : g.line.ga));
  const xs = xf.map((f, i) => share(f, xa[i])), gs = gf.map((f, i) => share(f, ga[i]));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="On-ice expected goal share over recent games" className="block h-auto w-full text-[11px]">
      {[0.25, 0.5, 0.75].map(v => (
        <g key={v}>
          <line x1={L - 3} x2={W - R} y1={Y(v)} y2={Y(v)} stroke={v === 0.5 ? "var(--grid)" : "var(--border)"} strokeDasharray={v === 0.5 ? undefined : "2 4"} />
          <text x={L - 6} y={Y(v) + 4} textAnchor="end" fill="var(--muted-foreground)">{v * 100}%</text>
        </g>
      ))}
      <text x={12} y={(base + top) / 2} transform={`rotate(-90 12 ${(base + top) / 2})`} textAnchor="middle" fill="var(--muted-foreground)">On ice</text>
      {rows.map((g, i) => (
        <circle key={g.id} cx={X(i)} cy={Y(xs[i] ?? 0.5)} r={2.5} fill="var(--home)">
          <title>{`Through ${label(g)}: ${five ? "5v5 " : ""}xG share ${xs[i] == null ? "–" : (xs[i]! * 100).toFixed(0) + "%"}, goal share ${gs[i] == null ? "–" : (gs[i]! * 100).toFixed(0) + "%"} over the last ${Math.min(k, i + 1)} games`}</title>
        </circle>
      ))}
      <polyline fill="none" stroke="var(--home)" strokeWidth={1.75} points={pts(xs, X, Y)} />
      <polyline fill="none" stroke="var(--foreground)" strokeWidth={1.5} strokeDasharray="5 4" points={pts(gs, X, Y)} />
      {(() => {
        const i = rows.length - 1, a = Y(xs[i] ?? 0.5), b = Y(gs[i] ?? 0.5);
        const [ya, yb] = Math.abs(a - b) < 28 ? (a <= b ? [a - 14, a + 16] : [b + 16, b - 14]) : [a, b];
        const p = (v: number | null) => (v == null ? "–" : `${Math.round(v * 100)}%`);
        return <>
          <EndLabel x={X(i)} y={ya} value={p(xs[i])} name="xG share" color="var(--home)" />
          <EndLabel x={X(i)} y={yb} value={p(gs[i])} name="goal share" color="var(--foreground)" />
        </>;
      })()}
    </svg>
  );
}

/** Goals saved above expected in each game, and the season's running total. */
function Saves({ rows }: { rows: LogRow[] }) {
  const router = useRouter();
  const H = 280, mid = 82, cTop = 188, cBase = H - 10;
  const per = rows.map(g => n(g.line.xga_) - n(g.line.ga_));
  let run = 0;
  const cum = per.map(v => (run += v));
  const m = Math.max(1, ...per.map(Math.abs)), c = Math.max(1, ...cum.map(Math.abs));
  const Y = (v: number) => mid - (v / m) * (mid - 12);
  const C = (v: number) => (cTop + cBase) / 2 - (v / c) * ((cBase - cTop) / 2);
  const X = xAt(rows.length), bw = barW(rows.length);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Goals saved above expected by game" className="block h-auto w-full text-[11px]">
      <line x1={L} x2={W - R} y1={mid} y2={mid} stroke="var(--grid)" />
      <text x={L - 6} y={mid + 4} textAnchor="end" fill="var(--muted-foreground)">0</text>
      {[m, -m].map(v => <text key={v} x={L - 6} y={Y(v) + 4} textAnchor="end" fill="var(--muted-foreground)">{v > 0 ? "+" : ""}{v.toFixed(1)}</text>)}
      <text x={12} y={mid} transform={`rotate(-90 12 ${mid})`} textAnchor="middle" fill="var(--muted-foreground)">GSAx</text>
      {rows.map((g, i) => {
        const v = per[i], x = X(i);
        return (
          <g key={g.id} className="cursor-pointer hover:opacity-70" onClick={() => router.push(`/game/${g.id}`)}>
            <title>{`${label(g)}: ${n(g.line.ga_)} GA on ${n(g.line.xga_).toFixed(2)} xGA, GSAx ${v > 0 ? "+" : ""}${v.toFixed(2)}`}</title>
            <rect x={x - bw / 2} y={Math.min(Y(v), mid)} width={bw} height={Math.max(1, Math.abs(Y(v) - mid))} rx={1.5} fill={v >= 0 ? "var(--good)" : "var(--bad)"} opacity={0.8} />
          </g>
        );
      })}
      <line x1={L} x2={W - R} y1={C(0)} y2={C(0)} stroke="var(--grid)" />
      <text x={L - 6} y={C(0) + 4} textAnchor="end" fill="var(--muted-foreground)">0</text>
      <text x={12} y={(cTop + cBase) / 2} transform={`rotate(-90 12 ${(cTop + cBase) / 2})`} textAnchor="middle" fill="var(--muted-foreground)">Total</text>
      <polyline fill="none" stroke="var(--foreground)" strokeWidth={1.5} opacity={0.75} points={pts(cum, X, C)} />
      <text x={W - R + 6} y={C(cum[cum.length - 1]) + 4} fill="var(--foreground)">{cum[cum.length - 1] > 0 ? "+" : ""}{cum[cum.length - 1].toFixed(1)}</text>
    </svg>
  );
}

const SPANS: [string, string][] = [["5", "5 games"], ["10", "10 games"]];
const STATES: [string, string][] = [["all", "All situations"], ["5v5", "5v5"]];

export function PlayerTrend({ rows, goalie }: { rows: LogRow[]; goalie: boolean }) {
  const [span, setSpan] = React.useState("5");
  const [state, setState] = React.useState("all");
  const five = state === "5v5";
  const k = +span;
  if (goalie) return (
    <>
      <Saves rows={rows} />
      <Note className="mt-2 text-xs">Bars are goals saved above expected in each game: green when he stopped more than an average goalie would have on the same shots. The line below is the season&apos;s running total. Click a bar to open the game.</Note>
    </>
  );
  return (
    <>
      {rows.length > 10 && (
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <Segmented label="Rolling average" value={span} onChange={setSpan} options={SPANS} />
          <span className="text-sm text-muted-foreground">rolling average</span>
        </div>
      )}
      <Key items={[
        { label: "ixG this game", kind: "bar", color: "var(--home)" },
        { label: "Goal", kind: "dot", color: "var(--foreground)" },
        { label: `ixG per game, last ${k}`, kind: "line", color: "var(--home)" },
        { label: `Goals per game, last ${k}`, kind: "dash", color: "var(--foreground)" },
      ]} />
      <Chances rows={rows} k={k} />
      <Note className="mb-6 mt-1 text-xs">Dashed above solid is finishing above his chances. Click a bar to open the game.</Note>
      <div className="mb-2 flex justify-end">
        <Segmented label="On-ice situations" value={state} onChange={setState} options={STATES} />
      </div>
      <Key items={[
        { label: `xG share with him on, last ${k}`, kind: "line", color: "var(--home)" },
        { label: `Goal share with him on, last ${k}`, kind: "dash", color: "var(--foreground)" },
      ]} />
      <OnIce rows={rows} k={k} five={five} />
      <Note className="mt-1 text-xs">
        {five ? "At 5-on-5." : "All situations. Penalty killers read low here: switch to 5v5 to leave out the short-handed minutes."}
      </Note>
    </>
  );
}

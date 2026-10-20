"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { LENSES, QCOL, type Quad, type StandingRow } from "@/lib/season";

interface Pt { t: StandingRow; x: number; y: number; q: Quad }

/** Every team on one of the four lenses, split into named quadrants: the
 *  chart and, separately, the list of teams in each quadrant. */
export function useLensChart({ rows, lens, season }: { rows: StandingRow[]; lens: string; season: number }) {
  const L = LENSES[lens];
  const router = useRouter();
  const [hover, setHover] = React.useState<{ p: Pt; x: number; y: number } | null>(null);

  const base = rows.map(t => ({ t, x: L.x(t), y: L.y(t) }))
    .filter((p): p is { t: StandingRow; x: number; y: number } => p.x != null && p.y != null && isFinite(p.x) && isFinite(p.y));
  if (!base.length) return { svg: <p className="text-sm text-muted-foreground">Not enough games yet.</p>, callouts: null };

  const avg = (a: number[]) => a.reduce((s, v) => s + v, 0) / a.length;
  const mx = L.mx ?? avg(base.map(p => p.x)), my = L.my ?? avg(base.map(p => p.y));
  const W = 560, H = 430, PL = 44, PR = 16, PT = 30, PB = 40;
  let x0 = Math.min(...base.map(p => p.x)), x1 = Math.max(...base.map(p => p.x));
  let y0 = Math.min(...base.map(p => p.y)), y1 = Math.max(...base.map(p => p.y));
  if (L.diag) { x0 = y0 = Math.min(x0, y0); x1 = y1 = Math.max(x1, y1); }
  const px = (x1 - x0) * 0.08 || 0.1, py = (y1 - y0) * 0.1 || 0.1;
  x0 -= px; x1 += px; y0 -= py; y1 += py;
  // keep the quadrant split inside the frame
  x0 = Math.min(x0, mx - px); x1 = Math.max(x1, mx + px); y0 = Math.min(y0, my - py); y1 = Math.max(y1, my + py);
  const X = (v: number) => { const f = (v - x0) / (x1 - x0); return PL + (L.flipX ? 1 - f : f) * (W - PL - PR); };
  const Y = (v: number) => { const f = (v - y0) / (y1 - y0); return PT + (L.flipY ? f : 1 - f) * (H - PT - PB); };
  const side = (p: { x: number; y: number }): Quad => {
    const hx = L.flipX ? p.x < mx : p.x >= mx, hy = L.flipY ? p.y < my : p.y >= my;
    return `${hx ? "h" : "l"}${hy ? "h" : "l"}` as Quad;
  };
  const pts: Pt[] = base.map(p => ({ ...p, q: side(p) }));
  const cx = X(mx), cy = Y(my);
  const box: Record<Quad, [number, number, number, number]> = {
    lh: [PL, PT, cx, cy], hh: [cx, PT, W - PR, cy], ll: [PL, cy, cx, H - PB], hl: [cx, cy, W - PR, H - PB],
  };

  const svg = (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${L.name} chart`} className="block h-auto w-full">
        {(Object.entries(box) as [Quad, number[]][]).map(([k, [a, b, c, d]]) => {
          const right = k[0] === "h", top = k[1] === "h";
          return (
            <g key={k}>
              <rect x={a} y={b} width={c - a} height={d - b} fill={QCOL[k]} opacity={0.07} />
              <text x={right ? c - 8 : a + 8} y={top ? b + 16 : d - 8} textAnchor={right ? "end" : "start"}
                fill={QCOL[k]} fontSize={11.5} fontWeight={600}>{L.q[k][0]}</text>
            </g>
          );
        })}
        <line x1={cx} x2={cx} y1={PT} y2={H - PB} stroke="oklch(1 0 0 / 0.14)" strokeDasharray="4 4" />
        <line y1={cy} y2={cy} x1={PL} x2={W - PR} stroke="oklch(1 0 0 / 0.14)" strokeDasharray="4 4" />
        {L.diag && (() => {
          const d = x0 + (x1 - x0) * 0.62;
          return (
            <>
              <line x1={X(x0)} y1={Y(x0)} x2={X(x1)} y2={Y(x1)} stroke="var(--muted-foreground)" opacity={0.6} />
              <text x={X(d) + 8} y={Y(d) + 16} fontSize={11} fill="var(--muted-foreground)">results = process</text>
            </>
          );
        })()}
        <text x={W - PR} y={H - 10} textAnchor="end" fontSize={11} fill="var(--muted-foreground)">{L.xl}</text>
        <text x={12} y={PT + 4} transform={`rotate(-90 12 ${PT + 4})`} textAnchor="end" fontSize={11} fill="var(--muted-foreground)">{L.yl}</text>
        {pts.map(p => (
          <g key={p.t.team} className="cursor-pointer"
            onMouseMove={e => setHover({ p, x: e.clientX, y: e.clientY })} onMouseLeave={() => setHover(null)}
            onClick={() => router.push(`/team/${season}/${p.t.team}`)}>
            <circle cx={X(p.x).toFixed(1)} cy={Y(p.y).toFixed(1)} r={4.2} fill={QCOL[p.q]} stroke="var(--card)" strokeWidth={1} />
            <text x={(X(p.x) + 6).toFixed(1)} y={(Y(p.y) + 3.5).toFixed(1)} fontSize={10} fill="var(--secondary-foreground)">{p.t.team}</text>
          </g>
        ))}
      </svg>
      {hover && (
        <div className="pointer-events-none fixed z-50 rounded-md border border-border bg-popover px-2.5 py-2 text-xs leading-relaxed [box-shadow:var(--shadow-l)]"
          style={{ left: Math.min(hover.x + 14, innerWidth - 240), top: hover.y + 14 }}>
          <div><b className="font-semibold">{hover.p.t.team}</b>, {L.q[hover.p.q][0].toLowerCase()}</div>
          <div>{L.xl.split(":")[0]}: <b className="tabular font-semibold">{L.fx(hover.p.x)}</b></div>
          <div>{L.yl.split(":")[0]}: <b className="tabular font-semibold">{L.fy(hover.p.y)}</b></div>
          <div className="text-muted-foreground">{hover.p.t.w}-{hover.p.t.l}-{hover.p.t.otl}, {hover.p.t.pts} pts</div>
        </div>
      )}
    </div>
  );

  // Each quadrant's teams, furthest from the split first.
  const sx = x1 - x0, sy = y1 - y0;
  const dist = (p: Pt) => Math.hypot((p.x - mx) / sx, (p.y - my) / sy);
  const teamLinks = (list: Pt[]) => list.map(p => (
    <Link key={p.t.team} href={`/team/${season}/${p.t.team}`} className="font-medium underline decoration-border underline-offset-4 hover:decoration-foreground">{p.t.team}</Link>
  ));
  const callout = (key: string, color: string, title: string, sub: React.ReactNode, body: React.ReactNode) => (
    <div key={key} className="well rounded-lg px-3 py-2.5 text-[13px]">
      <div className="font-semibold"><i className="mr-2 inline-block size-2 rounded-full align-[1px]" style={{ background: color }} />{title}</div>
      {sub && <div className="text-xs text-muted-foreground">{sub}</div>}
      <div className="mt-1 flex flex-wrap gap-x-2.5 gap-y-1">{body}</div>
    </div>
  );
  const extra: React.ReactNode[] = [];
  if (L.diag) {
    const gap = pts.map(p => ({ p, g: p.y - p.x })).sort((a, b) => a.g - b.g);
    const list = (xs: typeof gap) => xs.map(({ p, g }) => (
      <span key={p.t.team}>{teamLinks([p])} <span className="text-muted-foreground">{g > 0 ? "+" : ""}{(g * 100).toFixed(1)}%</span></span>
    ));
    extra.push(callout("unlucky", "var(--home)", "Unluckiest", "goal share furthest below chance share", list(gap.slice(0, 4))));
    extra.push(callout("lucky", "var(--warn)", "Luckiest", "goal share furthest above chance share", list(gap.slice(-4).reverse())));
  }
  const callouts = (
    <div className="grid gap-2">
      {extra}
      {(["hh", "hl", "lh", "ll"] as Quad[]).map(k => {
        const g = pts.filter(p => p.q === k).sort((a, b) => dist(b) - dist(a));
        return callout(k, QCOL[k], `${L.q[k][0]}, ${g.length}`, L.q[k][1], g.length ? teamLinks(g) : "–");
      })}
    </div>
  );
  return { svg, callouts };
}

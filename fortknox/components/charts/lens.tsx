"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { LENSES, lensQuads, QCOL, type Quad, type StandingRow } from "@/lib/season";

interface Pt { t: StandingRow; x: number; y: number; q: Quad }

const R = 4.2, LH = 10, CW = 6.3;

/** About five round-numbered ticks between lo and hi. */
function ticks(lo: number, hi: number) {
  const raw = (hi - lo) / 5, mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw)!;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(10));
  return out;
}

function tickFormat(kind: "num" | "pct" | "signed", t: number[]) {
  const step = t.length > 1 ? t[1] - t[0] : 1;
  const d = (k: number) => Math.max(0, -Math.floor(Math.log10(step * k) + 1e-9));
  if (kind === "pct") return (v: number) => (v * 100).toFixed(d(100)) + "%";
  if (kind === "signed") return (v: number) => (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(d(1));
  return (v: number) => v.toFixed(d(1));
}

type Box = [x: number, y: number, w: number, h: number];
const overlap = (a: Box, b: Box) =>
  Math.max(0, Math.min(a[0] + a[2], b[0] + b[2]) - Math.max(a[0], b[0])) * Math.max(0, Math.min(a[1] + a[3], b[1] + b[3]) - Math.max(a[1], b[1]));
interface Placed { x: number; y: number; box: Box; leader: boolean; lx: number; ly: number }

/** Puts each team's label beside its dot where it covers no dot and no other
 *  label, stepping further out (with a leader line) when the close spots are
 *  taken. Crowded points go first. */
function placeLabels(items: { key: string; x: number; y: number; text: string }[], frame: [number, number, number, number], r: number) {
  const dots: Box[] = items.map(p => [p.x - r - 1, p.y - r - 1, 2 * r + 2, 2 * r + 2]);
  const crowd = (p: { x: number; y: number }) => items.filter(q => Math.hypot(q.x - p.x, q.y - p.y) < 40).length;
  const order = [...items].sort((a, b) => crowd(b) - crowd(a));
  const taken: Box[] = [];
  const out = new Map<string, Placed>();
  for (const p of order) {
    const w = p.text.length * CW, h = LH;
    let best: { score: number; box: Box; d: number } | null = null;
    for (const d of [0, 8, 16, 26]) {
      const g = r + 2 + d;
      const cands: Box[] = [
        [p.x + g, p.y - h / 2, w, h], [p.x - g - w, p.y - h / 2, w, h],
        [p.x - w / 2, p.y - g - h, w, h], [p.x - w / 2, p.y + g, w, h],
        [p.x + g * 0.7, p.y - g * 0.7 - h, w, h], [p.x + g * 0.7, p.y + g * 0.7, w, h],
        [p.x - g * 0.7 - w, p.y - g * 0.7 - h, w, h], [p.x - g * 0.7 - w, p.y + g * 0.7, w, h],
      ];
      for (const b of cands) {
        if (b[0] < frame[0] + 1 || b[1] < frame[1] + 1 || b[0] + b[2] > frame[2] - 1 || b[1] + b[3] > frame[3] - 1) continue;
        const score = dots.reduce((s, o) => s + overlap(b, o), 0) * 4 + taken.reduce((s, o) => s + overlap(b, o), 0) + d * 0.01;
        if (!best || score < best.score) best = { score, box: b, d };
      }
      if (best && best.score < 1) break;
    }
    const b = best?.box ?? [p.x + r + 2, p.y - LH / 2, w, LH];
    taken.push(b);
    const lx = Math.min(Math.max(p.x, b[0]), b[0] + b[2]), ly = Math.min(Math.max(p.y, b[1]), b[1] + b[3]);
    out.set(p.key, { x: b[0], y: b[1], box: b, leader: (best?.d ?? 0) > 0, lx, ly });
  }
  return out;
}

/** A free spot along the diagonal for its label. */
function diagLabel(X: (v: number) => number, Y: (v: number) => number, v0: number, v1: number, dots: [number, number][], labels: Map<string, Placed>) {
  const w = 52, h = 11, others = [...labels.values()].map(l => l.box);
  for (const f of [0.82, 0.7, 0.9, 0.6, 0.5, 0.4, 0.3, 0.2]) {
    const v = v0 + (v1 - v0) * f;
    for (const [dx, dy] of [[8, 14], [-w - 8, -6]]) {
      const b: Box = [X(v) + dx, Y(v) + dy - h, w, h];
      if (!dots.some(([x, y]) => overlap(b, [x - R - 1, y - R - 1, 2 * R + 2, 2 * R + 2]) > 0) && !others.some(o => overlap(b, o) > 0))
        return { x: b[0], y: b[1] + h - 2 };
    }
  }
  return null;
}


/** Computer width: the chart takes the card's full width, with team logos. */
const LARGE = "(min-width: 1024px)";
const subscribeLarge = (f: () => void) => { const m = matchMedia(LARGE); m.addEventListener("change", f); return () => m.removeEventListener("change", f); };

/** Moves overlapping logos apart a little, so a cluster stays readable. Each
 *  spot shifts only as far as it must; the frame holds them in. */
function spreadOut(items: { key: string; x: number; y: number }[], min: number, frame: [number, number, number, number]) {
  const out = items.map(p => ({ ...p }));
  for (let it = 0; it < 60; it++) {
    let moved = false;
    for (let i = 0; i < out.length; i++) for (let j = i + 1; j < out.length; j++) {
      const a = out[i], b = out[j];
      let dx = b.x - a.x, dy = b.y - a.y;
      const d = Math.hypot(dx, dy);
      if (d >= min) continue;
      if (d < 1e-6) { dx = 1; dy = 0; }
      const k = (min - d) / 2 / (d || 1);
      a.x -= dx * k; a.y -= dy * k; b.x += dx * k; b.y += dy * k;
      moved = true;
    }
    for (const p of out) {
      p.x = Math.min(Math.max(p.x, frame[0] + min / 2), frame[2] - min / 2);
      p.y = Math.min(Math.max(p.y, frame[1] + min / 2), frame[3] - min / 2);
    }
    if (!moved) break;
  }
  return new Map(out.map(p => [p.key, { x: p.x, y: p.y }]));
}

/** Every team on one of the four lenses, split into quadrants: the chart and,
 *  separately, the list of teams in each quadrant. `focus` picks out some
 *  teams (a division, say): the rest fade to small dots, and drop out of the
 *  lists, but the quadrants still split at the league average.
 *
 *  With `from` (the season rows) the chart shows recent form: each team sits
 *  at its last-N-games spot, and a comet tail fades in from where it sat over
 *  the season. On a computer the teams are logos; narrower, labeled dots. */
export function useLensChart({ rows, lens, season, focus, from, window: n }: {
  rows: StandingRow[]; lens: string; season: number; focus?: Set<string> | null;
  /** With a recent-form window: the season rows, where each tail starts, and
   *  the window's length in games. `rows` is then the window. */
  from?: StandingRow[]; window?: number;
}) {
  const lit = (team: string) => !focus || focus.has(team);
  const L = LENSES[lens];
  const router = useRouter();
  const [hover, setHover] = React.useState<{ p: Pt; x: number; y: number } | null>(null);
  const logos = React.useSyncExternalStore(subscribeLarge, () => matchMedia(LARGE).matches, () => true);

  const base = rows.map(t => ({ t, x: L.x(t), y: L.y(t) }))
    .filter((p): p is { t: StandingRow; x: number; y: number } => p.x != null && p.y != null && isFinite(p.x) && isFinite(p.y));
  if (!base.length) return { svg: <p className="text-sm text-muted-foreground">Not enough games yet.</p>, callouts: null };

  const avg = (a: number[]) => a.reduce((s, v) => s + v, 0) / a.length;
  const mx = L.mx ?? avg(base.map(p => p.x)), my = L.my ?? avg(base.map(p => p.y));
  // Where each team sits over the season, for the tails. Movement is measured
  // in units of the spread across teams, so both axes count alike.
  const was = new Map<string, { x: number; y: number }>();
  for (const t of from ?? []) {
    const x = L.x(t), y = L.y(t);
    if (x != null && y != null && isFinite(x) && isFinite(y)) was.set(t.team, { x, y });
  }
  const spread = (a: number[]) => Math.max(...a) - Math.min(...a) || 1;
  const sxAll = spread(base.map(p => p.x)), syAll = spread(base.map(p => p.y));
  const moved = (p: { t: StandingRow; x: number; y: number }) => {
    const w = was.get(p.t.team);
    return w ? Math.hypot((p.x - w.x) / sxAll, (p.y - w.y) / syAll) : 0;
  };
  const movers = base.filter(p => was.has(p.t.team)).sort((a, b) => moved(b) - moved(a));
  const tailed = new Set(movers.filter(p => lit(p.t.team)).map(p => p.t.team));
  const ends = [...base, ...[...tailed].map(k => was.get(k)!)];
  // The plot sits between two bands that hold the quadrant labels, so the
  // labels never sit on top of a team.
  const [W, H] = logos ? [1000, 640] : [610, 520];
  const PL = 76, PR = 14, PT = 52, PB = 78, LS = 24;
  let x0 = Math.min(...ends.map(p => p.x)), x1 = Math.max(...ends.map(p => p.x));
  let y0 = Math.min(...ends.map(p => p.y)), y1 = Math.max(...ends.map(p => p.y));
  if (L.diag) { x0 = y0 = Math.min(x0, y0); x1 = y1 = Math.max(x1, y1); }
  const px = (x1 - x0) * 0.08 || 0.1, py = (y1 - y0) * 0.1 || 0.1;
  x0 -= px; x1 += px; y0 -= py; y1 += py;
  // keep the quadrant split inside the frame
  x0 = Math.min(x0, mx - px); x1 = Math.max(x1, mx + px); y0 = Math.min(y0, my - py); y1 = Math.max(y1, my + py);
  const X = (v: number) => { const f = (v - x0) / (x1 - x0); return PL + (L.flipX ? 1 - f : f) * (W - PL - PR); };
  const Y = (v: number) => { const f = (v - y0) / (y1 - y0); return PT + (L.flipY ? f : 1 - f) * (H - PT - PB); };
  const quads = lensQuads(rows, lens);
  const pts: Pt[] = base.map(p => ({ ...p, q: quads.get(p.t.team)! }));
  const cx = X(mx), cy = Y(my);
  const quadOf = (v: { x: number; y: number }): Quad =>
    `${(L.flipX ? v.x < mx : v.x >= mx) ? "h" : "l"}${(L.flipY ? v.y < my : v.y >= my) ? "h" : "l"}` as Quad;
  const box: Record<Quad, [number, number, number, number]> = {
    lh: [PL, PT, cx, cy], hh: [cx, PT, W - PR, cy], ll: [PL, cy, cx, H - PB], hl: [cx, cy, W - PR, H - PB],
  };
  const xt = ticks(x0, x1), yt = ticks(y0, y1);
  const fmtX = tickFormat(L.tx, xt), fmtY = tickFormat(L.ty, yt);
  const labels = placeLabels(pts.map(p => ({ key: p.t.team, x: X(p.x), y: Y(p.y), text: p.t.team })), [PL, PT, W - PR, H - PB], R);
  const diag = L.diag ? diagLabel(X, Y, x0, x1, pts.map(p => [X(p.x), Y(p.y)]), labels) : null;
  // Where each picked team's logo is drawn: its spot, nudged off its neighbours.
  const at = logos
    ? spreadOut(pts.filter(p => lit(p.t.team)).map(p => ({ key: p.t.team, x: X(p.x), y: Y(p.y) })), LS + 4, [PL, PT, W - PR, H - PB])
    : new Map<string, { x: number; y: number }>();
  const spot = (p: Pt) => at.get(p.t.team) ?? { x: X(p.x), y: Y(p.y) };

  /** A comet from the season spot `w` to now: a point at the season end,
   *  as wide as the marker at this end, fading in along the way. */
  const tail = (p: Pt, w: { x: number; y: number }) => {
    const a = { x: X(w.x), y: Y(w.y) }, b = spot(p);
    const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy);
    if (len < 2) return null;
    const half = logos ? LS * 0.32 : R * 0.9, nx = (-dy / len) * half, ny = (dx / len) * half;
    const id = `comet-${lens}-${p.t.team}`;
    return (
      <>
        <defs>
          <linearGradient id={id} gradientUnits="userSpaceOnUse" x1={a.x.toFixed(1)} y1={a.y.toFixed(1)} x2={b.x.toFixed(1)} y2={b.y.toFixed(1)}>
            <stop offset="0" stopColor={QCOL[p.q]} stopOpacity={0} />
            <stop offset="1" stopColor={QCOL[p.q]} stopOpacity={logos ? 0.45 : 0.6} />
          </linearGradient>
        </defs>
        <path d={`M${a.x.toFixed(1)},${a.y.toFixed(1)} L${(b.x + nx).toFixed(1)},${(b.y + ny).toFixed(1)} L${(b.x - nx).toFixed(1)},${(b.y - ny).toFixed(1)} Z`} fill={`url(#${id})`} />
      </>
    );
  };

  /** One team's marker: a logo in a quadrant-colored ring on a computer, a
   *  labeled dot narrower; a team that isn't picked is a small faint dot. */
  const marker = (p: Pt) => {
    if (!lit(p.t.team)) return <circle cx={X(p.x).toFixed(1)} cy={Y(p.y).toFixed(1)} r={logos ? 3.5 : R} fill={QCOL[p.q]} opacity={logos ? 0.3 : 0.15} />;
    if (logos) {
      const s = spot(p), r = LS / 2 + 2, img = LS - 4;
      return (
        <>
          <circle cx={s.x.toFixed(1)} cy={s.y.toFixed(1)} r={r} fill="var(--card)" stroke={QCOL[p.q]} strokeWidth={1.6} />
          <image href={`/logos/light/${p.t.team}.svg`} className="logo-light" x={(s.x - img / 2).toFixed(1)} y={(s.y - img / 2).toFixed(1)} width={img} height={img} />
          <image href={`/logos/${p.t.team}.svg`} className="logo-dark" x={(s.x - img / 2).toFixed(1)} y={(s.y - img / 2).toFixed(1)} width={img} height={img} />
        </>
      );
    }
    const lb = labels.get(p.t.team)!;
    return (
      <>
        {lb.leader && <line x1={X(p.x)} y1={Y(p.y)} x2={lb.lx} y2={lb.ly} stroke="var(--muted-foreground)" strokeWidth={0.6} opacity={0.6} />}
        <circle cx={X(p.x).toFixed(1)} cy={Y(p.y).toFixed(1)} r={R} fill={QCOL[p.q]} stroke="var(--card)" strokeWidth={1} />
        <text x={lb.x.toFixed(1)} y={(lb.y + LH - 2).toFixed(1)} fontSize={10} fill="var(--secondary-foreground)">{p.t.team}</text>
      </>
    );
  };

  const svg = (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${L.name} chart`} className="block h-auto w-full">
        {(Object.entries(box) as [Quad, number[]][]).map(([k, [a, b, c, d]]) => {
          const right = k[0] === "h", top = k[1] === "h";
          const tx = right ? W - PR : PL, ty = top ? 14 : H - 36;
          return (
            <g key={k}>
              <rect x={a} y={b} width={c - a} height={d - b} fill={QCOL[k]} opacity={0.07} />
              <text x={tx} y={ty} textAnchor={right ? "end" : "start"} fill={QCOL[k]} fontSize={11.5}>
                <tspan fontWeight={700}>{L.q[k][0]}</tspan>
                <tspan x={tx} dy={13} fontWeight={700}>{L.q[k][1]}</tspan>
                <tspan x={tx} dy={13} fontSize={10.5} opacity={0.85}>({L.q[k][2]})</tspan>
              </text>
            </g>
          );
        })}
        <rect x={PL} y={PT} width={W - PL - PR} height={H - PT - PB} fill="none" stroke="var(--grid)" />
        {xt.filter(v => Math.abs(X(v) - cx) > 48).map(v => (
          <g key={v}>
            <line x1={X(v)} x2={X(v)} y1={H - PB} y2={H - PB + 4} stroke="var(--muted-foreground)" />
            <text x={X(v)} y={H - PB + 15} textAnchor="middle" fontSize={10} fill="var(--muted-foreground)">{fmtX(v)}</text>
          </g>
        ))}
        {yt.filter(v => Math.abs(Y(v) - cy) > 16).map(v => (
          <g key={v}>
            <line x1={PL - 4} x2={PL} y1={Y(v)} y2={Y(v)} stroke="var(--muted-foreground)" />
            <text x={PL - 7} y={Y(v) + 3.5} textAnchor="end" fontSize={10} fill="var(--muted-foreground)">{fmtY(v)}</text>
          </g>
        ))}
        <line x1={cx} x2={cx} y1={PT} y2={H - PB + 4} stroke="var(--grid)" strokeDasharray="4 4" />
        <text x={cx} y={H - PB + 15} textAnchor="middle" fontSize={10} fontWeight={600} fill="var(--foreground)">{L.mxl ?? "League avg"} {L.fx(mx)}</text>
        <text x={PL - 7} y={cy - 2} textAnchor="end" fontSize={10} fontWeight={600} fill="var(--foreground)">
          <tspan>{L.fy(my)}</tspan>
          <tspan x={PL - 7} dy={11} fontSize={9} fontWeight={400} fill="var(--muted-foreground)">{L.myl ?? "Lg avg"}</tspan>
        </text>
        <line y1={cy} y2={cy} x1={PL} x2={W - PR} stroke="var(--grid)" strokeDasharray="4 4" />
        {L.diag && <line x1={X(x0)} y1={Y(x0)} x2={X(x1)} y2={Y(x1)} stroke="var(--muted-foreground)" opacity={0.6} />}
        {diag && <text x={diag.x} y={diag.y} fontSize={10.5} fill="var(--muted-foreground)">G% = xG%</text>}
        <text x={(PL + W - PR) / 2} y={H - PB + 32} textAnchor="middle" fontSize={11} fill="var(--muted-foreground)">{L.xl}</text>
        <text x={14} y={(PT + H - PB) / 2} transform={`rotate(-90 14 ${(PT + H - PB) / 2})`} textAnchor="middle" fontSize={11} fill="var(--muted-foreground)">{L.yl}</text>
        {/* all the tails under all the markers, faded teams under picked ones */}
        {pts.map(p => tailed.has(p.t.team) && <g key={`t-${p.t.team}`} className="pointer-events-none">{tail(p, was.get(p.t.team)!)}</g>)}
        {[...pts].sort((a, b) => +lit(a.t.team) - +lit(b.t.team)).map(p => (
          <g key={p.t.team} className="cursor-pointer"
            onMouseMove={e => setHover({ p, x: e.clientX, y: e.clientY })} onMouseLeave={() => setHover(null)}
            onClick={() => router.push(`/team/${season}/${p.t.team}`)}>
            {marker(p)}
          </g>
        ))}
      </svg>
      {hover && (
        <div className="pointer-events-none fixed z-50 rounded-md border border-border bg-popover px-2.5 py-2 text-xs leading-relaxed [box-shadow:var(--shadow-l)]"
          style={{ left: Math.min(hover.x + 14, innerWidth - 240), top: hover.y + 14 }}>
          <div><b className="font-semibold">{hover.p.t.team}</b> <span style={{ color: QCOL[hover.p.q] }}>{L.q[hover.p.q][2]}</span></div>
          <div>{L.xs}: <b className="tabular font-semibold">{L.fx(hover.p.x)}</b></div>
          <div>{L.ys}: <b className="tabular font-semibold">{L.fy(hover.p.y)}</b></div>
          {was.has(hover.p.t.team) && (
            <div className="text-muted-foreground">Season: {L.fx(was.get(hover.p.t.team)!.x)}, {L.fy(was.get(hover.p.t.team)!.y)}</div>
          )}
          <div className="text-muted-foreground">{hover.p.t.w}-{hover.p.t.l}-{hover.p.t.otl}, {hover.p.t.pts} pts{n ? ` in the last ${n}` : ""}</div>
        </div>
      )}
    </div>
  );

  // Each quadrant's teams, furthest from the split first.
  const sx = x1 - x0, sy = y1 - y0;
  const dist = (p: Pt) => Math.hypot((p.x - mx) / sx, (p.y - my) / sy);
  const teamLinks = (all: Pt[]) => all.filter(p => lit(p.t.team)).map(p => (
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
  if (was.size) {
    // Each axis that moved by a tenth of the league's spread or more, with an
    // arrow for its direction, green when the change is the good way.
    const axis = (d: number, spreadOf: number, flip: boolean | undefined, name: string) => {
      if (Math.abs(d) / spreadOf < 0.1) return null;
      const good = flip ? d < 0 : d > 0;
      return <span key={name} className={good ? "text-good" : "text-bad"}>{name} {d > 0 ? "↑" : "↓"}</span>;
    };
    const shown = movers.filter(p => lit(p.t.team)).slice(0, 4).map(m => pts.find(p => p.t.team === m.t.team)!);
    extra.push(callout("movers", "var(--muted-foreground)", `Biggest moves, last ${n} vs. season`, null,
      <div className="grid w-full gap-1">
        {shown.map(p => {
          const w = was.get(p.t.team)!, fromQ = quadOf(w);
          const parts = [axis(p.x - w.x, sxAll, L.flipX, L.xs), axis(p.y - w.y, syAll, L.flipY, L.ys)].filter(Boolean);
          return (
            <div key={p.t.team} className="flex flex-wrap items-baseline gap-x-2">
              {teamLinks([p])}
              {parts.length ? parts : <span className="text-muted-foreground">small moves</span>}
              {fromQ !== p.q && (
                <span className="text-muted-foreground">
                  <i className="mr-1 inline-block size-1.5 rounded-full align-[1px]" style={{ background: QCOL[fromQ] }} />→
                  <i className="ml-1 mr-1 inline-block size-1.5 rounded-full align-[1px]" style={{ background: QCOL[p.q] }} />{L.q[p.q][2].toLowerCase()}
                </span>
              )}
            </div>
          );
        })}
      </div>));
  }
  if (L.diag) {
    const gap = pts.map(p => ({ p, g: p.y - p.x })).sort((a, b) => a.g - b.g);
    const list = (xs: typeof gap) => xs.map(({ p, g }) => (
      <span key={p.t.team}>{teamLinks([p])} <span className="text-muted-foreground">{g > 0 ? "+" : ""}{(g * 100).toFixed(1)}%</span></span>
    ));
    const shown = gap.filter(({ p }) => lit(p.t.team));
    extra.push(callout("unlucky", "var(--home)", "G% furthest below xG%", null, list(shown.slice(0, 4))));
    extra.push(callout("lucky", "var(--warn)", "G% furthest above xG%", null, list(shown.slice(-4).reverse())));
  }
  const callouts = (
    <div className="grid gap-2">
      {extra}
      {(["hh", "hl", "lh", "ll"] as Quad[]).map(k => {
        const g = pts.filter(p => p.q === k && lit(p.t.team)).sort((a, b) => dist(b) - dist(a));
        return callout(k, QCOL[k], `${L.q[k][0]} ${L.q[k][1]}`, L.q[k][2], g.length ? teamLinks(g) : "–");
      })}
    </div>
  );
  return { svg, callouts };
}

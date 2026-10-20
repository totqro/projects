import { ORD } from "@/lib/format";
import type { Shot } from "@/lib/types";

/** Cumulative expected goals over the game, one line per team; dots are goals. */
export function FlowChart({ shots, home, away }: { shots: Shot[]; home: string; away: string }) {
  const W = 420, H = 250, L = 26, R = 8, T = 10, B = 24;
  const end = Math.max(3600, ...shots.map(s => (s.p - 1) * 1200 + s.t));
  const series = (team: string) => {
    let c = 0;
    const pts: [number, number][] = [[0, 0]], goals: [number, number][] = [];
    shots.filter(s => s.team === team && s.ev !== "BLOCK").forEach(s => {
      const g = (s.p - 1) * 1200 + s.t;
      pts.push([g, c]); c += s.xg; pts.push([g, c]);
      if (s.ev === "GOAL") goals.push([g, c]);
    });
    pts.push([end, c]);
    return { pts, goals, total: c };
  };
  const h = series(home), a = series(away);
  const ymax = Math.max(1, Math.ceil(Math.max(h.total, a.total) + 0.3));
  const X = (t: number) => L + (t / end) * (W - L - R);
  const Y = (v: number) => T + (1 - v / ymax) * (H - T - B);
  const grid: number[] = [];
  for (let v = 0; v <= ymax; v += ymax > 6 ? 2 : 1) grid.push(v);
  const periods: number[] = [];
  for (let p = 0; p * 1200 < end; p++) periods.push(p);
  // End labels: nudge apart when the two totals finish close together.
  let ya = Y(a.total) - 5, yh = Y(h.total) - 5;
  if (Math.abs(ya - yh) < 13) { if (a.total >= h.total) yh = ya + 13; else ya = yh + 13; }
  const lines = [
    { s: a, col: "var(--away)", ab: away, ly: ya },
    { s: h, col: "var(--home)", ab: home, ly: yh },
  ];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Cumulative expected goals" className="block h-auto w-full text-[11px]">
      {grid.map(v => (
        <g key={v}>
          <line x1={L} x2={W - R} y1={Y(v)} y2={Y(v)} stroke="var(--border)" strokeDasharray="3 3" />
          <text x={L - 6} y={Y(v) + 3} textAnchor="end" fill="var(--muted-foreground)">{v}</text>
        </g>
      ))}
      {periods.slice(1).map(p => <line key={p} x1={X(p * 1200)} x2={X(p * 1200)} y1={T} y2={H - B} stroke="oklch(1 0 0 / 0.14)" />)}
      {periods.map(p => (
        <text key={p} x={(X(p * 1200) + X(Math.min(end, (p + 1) * 1200))) / 2} y={H - 8} textAnchor="middle" fill="var(--muted-foreground)">{ORD(p + 1)}</text>
      ))}
      {lines.map(({ s, col, ab, ly }) => (
        <g key={ab}>
          <polyline fill="none" stroke={col} strokeWidth={2} points={s.pts.map(p => `${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join(" ")} />
          {s.goals.map(([t, v], i) => <circle key={i} cx={X(t)} cy={Y(v)} r={4} fill={col} stroke="var(--ring-goal)" strokeWidth={1.2} />)}
          <text x={W - R - 2} y={ly} textAnchor="end" fill={col} fontWeight={600}>{ab} {s.total.toFixed(2)}</text>
        </g>
      ))}
    </svg>
  );
}

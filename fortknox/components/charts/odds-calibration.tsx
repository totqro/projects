export interface OddsBin { lo: number; hi: number; n: number; pred: number; obs: number }

/** Back-tested playoff odds against what happened: one dot per band of
 *  predicted odds, sized by how many team-seasons fell in it. Dots on the
 *  diagonal mean "70%" came true about 70% of the time. */
export function OddsCalibrationChart({ bins }: { bins: OddsBin[] }) {
  const W = 520, H = 360, L = 52, R = 16, T = 14, B = 44;
  const X = (v: number) => L + v * (W - L - R);
  const Y = (v: number) => H - B - v * (H - T - B);
  const ticks = [0, 0.2, 0.4, 0.6, 0.8, 1];
  const pc = (v: number) => `${Math.round(v * 100)}%`;
  const maxN = Math.max(...bins.map(b => b.n));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Back-test: predicted playoff odds against the share that made it" className="block h-auto w-full max-w-xl text-[11px]">
      {ticks.map(v => (
        <g key={v}>
          <line x1={L} x2={W - R} y1={Y(v)} y2={Y(v)} stroke="var(--border)" strokeDasharray="2 4" />
          <text x={L - 8} y={Y(v) + 4} textAnchor="end" fill="var(--muted-foreground)">{pc(v)}</text>
          <text x={X(v)} y={H - B + 16} textAnchor="middle" fill="var(--muted-foreground)">{pc(v)}</text>
        </g>
      ))}
      <line x1={X(0)} y1={Y(0)} x2={X(1)} y2={Y(1)} stroke="var(--muted-foreground)" strokeDasharray="5 4" opacity={0.7} />
      <text x={X(0.8)} y={Y(0.6)} fill="var(--muted-foreground)">perfect</text>
      <text x={(L + W - R) / 2} y={H - 6} textAnchor="middle" fill="var(--muted-foreground)">Projected playoff odds →</text>
      <text x={14} y={(T + H - B) / 2} transform={`rotate(-90 14 ${(T + H - B) / 2})`} textAnchor="middle" fill="var(--muted-foreground)">Share that made it ↑</text>
      {bins.map(b => (
        <g key={b.lo}>
          <title>{`Odds ${pc(b.lo)}–${pc(b.hi)}: ${b.n} team-seasons, projected ${(b.pred * 100).toFixed(1)}% on average, ${(b.obs * 100).toFixed(1)}% made it`}</title>
          <circle cx={X(b.pred)} cy={Y(b.obs)} r={4 + 6 * Math.sqrt(b.n / maxN)} fill="var(--brand)" stroke="var(--card)" strokeWidth={2} />
        </g>
      ))}
    </svg>
  );
}

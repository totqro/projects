import type { CalBin } from "@/lib/model";

/** Predicted against actual goal rate, one dot per xG bin with its 95%
 *  interval. Dots on the diagonal mean the model's probabilities are right. */
export function CalibrationChart({ bins }: { bins: CalBin[] }) {
  const W = 520, H = 360, L = 52, R = 16, T = 14, B = 44;
  const max = Math.min(1, Math.ceil(Math.max(0.3, ...bins.map(b => Math.max(b.ciHi, b.xg / b.n))) * 10) / 10);
  const X = (v: number) => L + (v / max) * (W - L - R);
  const Y = (v: number) => H - B - (v / max) * (H - T - B);
  const ticks = Array.from({ length: Math.round(max / 0.1) + 1 }, (_, i) => +(i * 0.1).toFixed(1));
  const pc = (v: number) => `${Math.round(v * 100)}%`;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Calibration: predicted against actual goal rate" className="block h-auto w-full max-w-xl text-[11px]">
      {ticks.map(v => (
        <g key={v}>
          <line x1={L} x2={W - R} y1={Y(v)} y2={Y(v)} stroke="var(--border)" strokeDasharray="2 4" />
          <text x={L - 8} y={Y(v) + 4} textAnchor="end" fill="var(--muted-foreground)">{pc(v)}</text>
          <text x={X(v)} y={H - B + 16} textAnchor="middle" fill="var(--muted-foreground)">{pc(v)}</text>
        </g>
      ))}
      <line x1={X(0)} y1={Y(0)} x2={X(max)} y2={Y(max)} stroke="var(--muted-foreground)" strokeDasharray="5 4" opacity={0.7} />
      <text x={X(max) - 4} y={Y(max) + 14} textAnchor="end" fill="var(--muted-foreground)">perfect</text>
      <text x={(L + W - R) / 2} y={H - 6} textAnchor="middle" fill="var(--muted-foreground)">Predicted (average xG in the bin) →</text>
      <text x={14} y={(T + H - B) / 2} transform={`rotate(-90 14 ${(T + H - B) / 2})`} textAnchor="middle" fill="var(--muted-foreground)">Actual goal rate ↑</text>
      {bins.map(b => {
        const x = X(b.xg / b.n);
        return (
          <g key={b.lo}>
            <title>{`xG ${pc(b.lo)}–${pc(b.hi)}: ${b.n.toLocaleString("en-US")} shots, predicted ${(b.xg / b.n * 100).toFixed(1)}%, scored ${(b.rate * 100).toFixed(1)}% (${b.goals} goals; 95% range ${(b.ciLo * 100).toFixed(1)}–${(b.ciHi * 100).toFixed(1)}%)`}</title>
            <line x1={x} x2={x} y1={Y(b.ciLo)} y2={Y(b.ciHi)} stroke="var(--brand-dim)" strokeWidth={2} strokeLinecap="round" />
            <circle cx={x} cy={Y(b.rate)} r={5} fill="var(--brand)" stroke="var(--card)" strokeWidth={2} />
            <circle cx={x} cy={Y(b.rate)} r={14} fill="transparent" />
          </g>
        );
      })}
    </svg>
  );
}

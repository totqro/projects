import { margins, sides } from "@/lib/deserve";
import { nickname } from "@/lib/teams";
import type { Sheet } from "@/lib/types";
import { Note } from "@/components/site/section";

// Deserve to win on the game page: each team's chance of winning had the
// game's shots been taken again, and how often each final margin comes up.

const M = 4;
const W = 400, H = 150, top = 18, base = 112, L = 6, R = 6;
const pct0 = (v: number) => `${Math.round(v * 100)}%`;

export function DeserveToWin({ G }: { G: Sheet }) {
  const { h, a } = sides(G.shots, G.home.abbrev);
  const { margins: m, hwin } = margins(h, a, M);
  const awin = 1 - hwin;
  // How it finished on the same shots: goals, empty-net ones aside.
  const goals = (team: string) => G.shots.filter(s => s.team === team && s.ev === "GOAL" && s.sit !== "EN_AGAINST").length;
  const actual = Math.max(-M, Math.min(M, goals(G.home.abbrev) - goals(G.away.abbrev)));
  const max = Math.max(...m);
  const slot = (W - L - R) / m.length, bw = slot - 6;
  const x = (i: number) => L + i * slot + 3;
  const label = (d: number) => (d === 0 ? "Tie" : `${d < 0 ? G.away.abbrev : G.home.abbrev} ${Math.abs(d)}${Math.abs(d) === M ? "+" : ""}`);
  return (
    <div>
      <div className="flex items-end justify-between gap-3">
        <div>
          <div className="tabular font-[family-name:var(--font-display)] text-[28px] font-bold leading-none text-away">{pct0(awin)}</div>
          <div className="mt-1 text-xs text-muted-foreground">{nickname(G.away.name)}</div>
        </div>
        <div className="text-right">
          <div className="tabular font-[family-name:var(--font-display)] text-[28px] font-bold leading-none text-home">{pct0(hwin)}</div>
          <div className="mt-1 text-xs text-muted-foreground">{nickname(G.home.name)}</div>
        </div>
      </div>
      <div className="mt-2.5 flex h-2 gap-px overflow-hidden rounded-full [box-shadow:var(--shadow-inset)]" aria-hidden="true">
        <i className="block bg-away" style={{ flex: awin }} />
        <i className="block bg-home" style={{ flex: hwin }} />
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" className="mt-4 block h-auto w-full text-[11px]"
        aria-label={`Chance of each final margin on these shots: ${m.map((v, i) => `${label(i - M)} ${pct0(v)}`).join(", ")}`}>
        <line x1={L} x2={W - R} y1={base} y2={base} stroke="var(--grid)" />
        {m.map((v, i) => {
          const d = i - M, hgt = max ? (v / max) * (base - top) : 0;
          const fill = d < 0 ? "var(--away)" : d > 0 ? "var(--home)" : "var(--muted-foreground)";
          return (
            <g key={d}>
              <title>{`${label(d)}: ${(v * 100).toFixed(1)}%`}</title>
              <rect x={x(i)} y={base - hgt} width={bw} height={hgt} rx={2} fill={fill} opacity={d === actual ? 0.95 : 0.5} />
              {d === actual && <rect x={x(i) - 1.5} y={base - hgt - 1.5} width={bw + 3} height={hgt + 1.5} rx={3} fill="none" stroke="var(--foreground)" strokeWidth={1.25} />}
              <text x={x(i) + bw / 2} y={base - hgt - 5} textAnchor="middle" fill="var(--muted-foreground)">{v >= 0.005 ? pct0(v) : ""}</text>
              <text x={x(i) + bw / 2} y={base + 14} textAnchor="middle" fill={d === actual ? "var(--foreground)" : "var(--muted-foreground)"}>{d === 0 ? "Tie" : `${Math.abs(d)}${Math.abs(d) === M ? "+" : ""}`}</text>
            </g>
          );
        })}
        <text x={L} y={H - 4} fill="var(--away)">← {G.away.abbrev} wins by</text>
        <text x={W - R} y={H - 4} textAnchor="end" fill="var(--home)">{G.home.abbrev} wins by →</text>
      </svg>
      <Note className="mt-2 text-xs">
        Each team&apos;s chance of winning had these shots been taken again, every one going in with its xG as the chance. Empty-net shots
        are left out, and a tie counts as a coin flip, like a shootout. The bars are how often each final margin comes up; the outlined one is
        how {G.live?.state === "live" ? "it stands" : "it finished"}, empty-net goals aside.
      </Note>
    </div>
  );
}

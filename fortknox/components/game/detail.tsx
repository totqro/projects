import { periods } from "@/lib/game";
import { nickname } from "@/lib/teams";
import type { Sheet } from "@/lib/types";

// The game page's "In detail" charts: where each team's numbers rank among
// the season's team-games, and the chances period by period.

/** One team's figure for the game and its percentile among the season's
 *  team-games (0-100), worked out at build time (app/game/[id]/page.tsx). */
export interface Rank { value: string; pct: number }
export interface TeamRanks { xgs: Rank; xg: Rank; sog: Rank }
export interface GameRanks { away: TeamRanks; home: TeamRanks; teams: number }

// Poor to great: blue through a neutral grey to orange, so the scale reads
// without red/green.
const POOR = [47, 109, 181], MID = [168, 160, 147], GREAT = [180, 72, 26];
const mix = (a: number[], b: number[], t: number) => `rgb(${a.map((v, i) => Math.round(v + (b[i] - v) * t)).join(" ")})`;
const scale = (p: number) => (p < 50 ? mix(POOR, MID, p / 50) : mix(MID, GREAT, (p - 50) / 50));

const ROWS: [keyof TeamRanks, string][] = [["xgs", "xG share"], ["xg", "Expected goals"], ["sog", "Shots on goal"]];

function Slider({ label, r }: { label: string; r: Rank }) {
  const c = scale(r.pct), left = Math.min(Math.max(r.pct, 0), 100);
  return (
    <div className="grid grid-cols-[minmax(0,7rem)_minmax(0,1fr)_3rem] items-center gap-2.5 py-1.5">
      <span className="text-right text-[13px]">{label}</span>
      <div className="relative h-2 bg-muted" role="img" aria-label={`${label}: ${r.value}, ${r.pct}th percentile`}>
        <div className="absolute inset-y-0 left-0" style={{ width: `${left}%`, background: c, opacity: 0.75 }} />
        <span className="tabular absolute top-1/2 grid size-[22px] -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border-2 border-background text-[10px] font-bold text-white"
          style={{ left: `clamp(11px, ${left}%, calc(100% - 11px))`, background: c }}>{r.pct}</span>
      </div>
      <span className="tabular text-right text-[13px]">{r.value}</span>
    </div>
  );
}

export function GamePercentiles({ G, ranks }: { G: Sheet; ranks: GameRanks }) {
  const team = (side: "away" | "home") => (
    <div className="mt-2">
      <div className={`text-xs font-bold uppercase tracking-[0.06em] ${side === "away" ? "text-away" : "text-home"}`}>{nickname(G[side].name)}</div>
      {ROWS.map(([k, l]) => <Slider key={k} label={l} r={ranks[side][k]} />)}
    </div>
  );
  return (
    <div>
      <p className="mb-1 text-[13px] text-muted-foreground">Against all {ranks.teams.toLocaleString("en-US")} team-games of the season</p>
      <div className="grid grid-cols-[minmax(0,7rem)_minmax(0,1fr)_3rem] gap-2.5 text-[11px] font-semibold uppercase tracking-[0.06em]">
        <span /><span className="flex justify-between"><span style={{ color: scale(0) }}>Poor</span><span className="text-muted-foreground">Average</span><span style={{ color: scale(100) }}>Great</span></span><span />
      </div>
      {team("home")}
      {team("away")}
    </div>
  );
}

/** xG for in each period, the home team's bars up and the away team's down. */
export function ChancesByPeriod({ G }: { G: Sheet }) {
  const P = periods(G);
  const [away, home] = P.xg;
  const n = P.ps.length, W = 420, mid = 85, span = 66;
  const max = Math.max(0.5, ...home.by, ...away.by);
  const slot = W / n, bw = Math.min(90, slot - 30);
  const x = (i: number) => i * slot + (slot - bw) / 2;
  const name = (p: number) => (p <= 3 ? ["1st", "2nd", "3rd"][p - 1] : p === 4 ? "OT" : `${p - 3}OT`);
  return (
    <div>
      <p className="mb-2 text-[13px] text-muted-foreground">xG for, {nickname(G.home.name)} up, {nickname(G.away.name)} down</p>
      <svg viewBox={`0 0 ${W} 192`} role="img" className="block h-auto w-full max-w-[460px] text-[13px]"
        aria-label={`xG by period: ${P.ps.map((p, i) => `${name(p)} ${G.home.abbrev} ${home.by[i].toFixed(2)}, ${G.away.abbrev} ${away.by[i].toFixed(2)}`).join("; ")}`}>
        <line x1={0} x2={W} y1={mid} y2={mid} stroke="var(--foreground)" />
        {P.ps.map((p, i) => {
          const hh = (home.by[i] / max) * span, ah = (away.by[i] / max) * span;
          return (
            <g key={p}>
              <rect x={x(i)} y={mid - hh} width={bw} height={hh} fill="var(--home)" />
              <rect x={x(i)} y={mid} width={bw} height={ah} fill="var(--away)" />
              <text x={x(i) + bw / 2} y={mid - hh - 6} textAnchor="middle" fontWeight={600} fill="var(--foreground)">{home.by[i].toFixed(2)}</text>
              <text x={x(i) + bw / 2} y={mid + ah + 15} textAnchor="middle" fontWeight={600} fill="var(--foreground)">{away.by[i].toFixed(2)}</text>
              <text x={x(i) + bw / 2} y={188} textAnchor="middle" fontSize={12} fill="var(--muted-foreground)">{name(p)}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

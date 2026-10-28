"use client";

import * as React from "react";
import { seasonLabel } from "@/lib/format";
import { Segmented } from "@/components/teams/teams-view";

// The Model page's predictive check (pipeline/fit_validation.py): how well
// each team number over the first N games predicts points % over the rest.

export interface Validation {
  seasons: number[];
  min_rest: number;
  n: number[];
  teams: number[];
  r: Record<string, (number | null)[]>;
  last: { season: number; r: Record<string, (number | null)[]> };
}

const LINES: { k: string; label: string; color: string; width: number; dash?: string }[] = [
  { k: "xgs5", label: "5v5 xG share", color: "var(--brand)", width: 2.5 },
  { k: "pts", label: "Points %", color: "var(--foreground)", width: 2.5 },
  { k: "xgs", label: "xG share, all situations", color: "var(--home)", width: 1.5, dash: "5 4" },
  { k: "dpts", label: "Deserved points %", color: "var(--warn)", width: 1.5, dash: "2 3" },
  { k: "gs", label: "Goal share", color: "var(--muted-foreground)", width: 1.5, dash: "5 4" },
];

const W = 640, H = 330, L = 46, R = 16, T = 14, B = 42;

/** The first N where points % catches 5v5 xG share, past the opening noise. */
const crossing = (r: Validation["r"], n: number[]) =>
  n.find((v, i) => v > 10 && r.pts[i] != null && r.xgs5[i] != null && r.pts[i]! >= r.xgs5[i]!);

export function ValidationChart({ data }: { data: Validation }) {
  const [view, setView] = React.useState("all");
  const r = view === "all" ? data.r : data.last.r;
  const n = data.n, maxN = n[n.length - 1];
  const X = (v: number) => L + ((v - 1) / (maxN - 1)) * (W - L - R);
  const Y = (v: number) => H - B - (v / 0.7) * (H - T - B);
  const cross = crossing(r, n);
  const path = (vals: (number | null)[]) =>
    vals.flatMap((v, i) => (v == null ? [] : [`${i && vals[i - 1] != null ? "L" : "M"}${X(n[i]).toFixed(1)},${Y(Math.max(0, v)).toFixed(1)}`])).join("");
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <Segmented label="Seasons" value={view} onChange={setView}
          options={[["all", `All ${data.seasons.length} seasons`], ["last", `${seasonLabel(data.last.season)} only`]]} />
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          {LINES.map(l => (
            <li key={l.k} className="inline-flex items-center gap-1.5">
              <svg width="18" height="6" aria-hidden="true"><line x1="0" x2="18" y1="3" y2="3" stroke={l.color} strokeWidth={l.width} strokeDasharray={l.dash} /></svg>
              {l.label}
            </li>
          ))}
        </ul>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" className="block h-auto w-full text-[11px]"
        aria-label={`How well each number over a team's first games predicts its points % over the rest of the season, ${view === "all" ? `${seasonLabel(data.seasons[0])} to ${seasonLabel(data.seasons[data.seasons.length - 1])}` : seasonLabel(data.last.season)}`}>
        {[0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7].map(v => (
          <g key={v}>
            <line x1={L} x2={W - R} y1={Y(v)} y2={Y(v)} stroke="var(--border)" strokeDasharray={v ? "2 4" : undefined} />
            <text x={L - 8} y={Y(v) + 4} textAnchor="end" fill="var(--muted-foreground)">{v.toFixed(1)}</text>
          </g>
        ))}
        {[1, 10, 20, 30, 41, 50, 60].map(v => (
          <text key={v} x={X(v)} y={H - B + 16} textAnchor="middle" fill="var(--muted-foreground)">{v}</text>
        ))}
        <text x={(L + W - R) / 2} y={H - 6} textAnchor="middle" fill="var(--muted-foreground)">Games played so far →</text>
        <text x={12} y={(T + H - B) / 2} transform={`rotate(-90 12 ${(T + H - B) / 2})`} textAnchor="middle" fill="var(--muted-foreground)">How well it predicts the rest (r) ↑</text>
        {cross && (
          <g>
            <line x1={X(cross)} x2={X(cross)} y1={T} y2={H - B} stroke="var(--muted-foreground)" strokeDasharray="3 3" opacity={0.6} />
            <text x={X(cross) + 5} y={T + 10} fill="var(--muted-foreground)">Points % catches up: game {cross}</text>
          </g>
        )}
        {[...LINES].reverse().map(l => (
          <path key={l.k} d={path(r[l.k])} fill="none" stroke={l.color} strokeWidth={l.width} strokeDasharray={l.dash} strokeLinejoin="round" />
        ))}
        {n.map((v, i) => (
          <g key={v}>
            <title>{`After ${v} games: ${LINES.map(l => `${l.label} ${r[l.k][i] == null ? "–" : r[l.k][i]!.toFixed(2)}`).join(", ")}`}</title>
            <rect x={X(v) - (W - L - R) / (maxN - 1) / 2} y={T} width={(W - L - R) / (maxN - 1)} height={H - T - B} fill="transparent" />
          </g>
        ))}
      </svg>
    </div>
  );
}

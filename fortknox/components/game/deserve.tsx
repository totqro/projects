import { Info } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { margins, sides } from "@/lib/deserve";
import { nickname } from "@/lib/teams";
import type { Sheet } from "@/lib/types";

// Deserve to win on the game page: each team's chance of winning had the
// game's shots been taken again, as a split meter against the 50% line, and
// below it how often each final margin comes up.

const M = 4;
const W = 440, base = 170, top = 30;
const pct0 = (v: number) => `${Math.round(v * 100)}%`;
const DISPLAY = "font-[family-name:var(--font-display)]";

export function DeserveToWin({ G }: { G: Sheet }) {
  const { h, a } = sides(G.shots, G.home.abbrev);
  const { margins: m, hwin } = margins(h, a, M);
  const awin = 1 - hwin;
  // How it finished on the same shots: goals, empty-net ones aside.
  const goals = (team: string) => G.shots.filter(s => s.team === team && s.ev === "GOAL" && s.sit !== "EN_AGAINST").length;
  const actual = Math.max(-M, Math.min(M, goals(G.home.abbrev) - goals(G.away.abbrev)));
  const max = Math.max(...m);
  const slot = W / m.length, bw = slot - 10;
  const x = (i: number) => i * slot + 5;
  const label = (d: number) => (d === 0 ? "Tie" : `${d < 0 ? G.away.abbrev : G.home.abbrev} by ${Math.abs(d)}${Math.abs(d) === M ? "+" : ""}`);
  const live = G.live?.state === "live";
  // Teams that shot at an empty net: those shots count in the xG at the top
  // but not here, which can flip who looks better. Named in the (i).
  const en = [G.away, G.home].filter(t => G.shots.some(s => s.team === t.abbrev && s.sit === "EN_AGAINST" && s.ev !== "BLOCK" && s.xg > 0));
  const enNames = en.map(t => nickname(t.name)).join(" and ");
  const enPoss = en.length && /s$/.test(nickname(en[en.length - 1].name)) ? "’" : "’s";
  return (
    <div>
      <p className="mb-2 text-[13px] text-muted-foreground">
        {live ? "So far: replay" : "Replay"} the shots, each going in with its xG as the chance.{" "}
        <Popover>
          <PopoverTrigger aria-label="How deserve to win works"
            className="inline-flex size-[18px] translate-y-[3px] items-center justify-center rounded-full text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring">
            <Info className="size-[15px]" aria-hidden="true" />
          </PopoverTrigger>
          <PopoverContent className="w-80 space-y-2 text-[13px] leading-snug">
            <p>Every unblocked shot gets another try, going in with its xG as the chance: a 0.20 xG shot scores one time in five.</p>
            <p>Played out over every combination, that gives how often each final margin comes up (the bars below). Deserve to win is how often each team comes out ahead, with ties split evenly, as an overtime coin flip.</p>
            <p>It isn’t just the xG totals: how the xG is spread across shots matters too, so in a close game the team with a little more xG can still come out under 50%.</p>
            <p>Shots at an empty net are left out, since they pad the leading team’s xG once the game is settled.{en.length > 0 && <> Here that’s the {enNames}{enPoss} shots, which the expected goals at the top still count.</>}</p>
          </PopoverContent>
        </Popover>
      </p>
      <div className="relative h-[34px]" aria-hidden="true">
        <div className="absolute inset-x-0 top-[9px] flex h-4">
          <i className="block bg-away" style={{ width: `${awin * 100}%` }} />
          <i className="block bg-home" style={{ width: `${hwin * 100}%` }} />
        </div>
        <div className="absolute inset-y-0.5 left-1/2 w-0.5 -translate-x-px bg-foreground" />
      </div>
      <div className="flex items-baseline justify-between leading-tight">
        <span><b className={`${DISPLAY} tabular text-[28px] font-black text-away`}>{pct0(awin)}</b> <span className="text-[12.5px] text-muted-foreground">{nickname(G.away.name)}</span></span>
        <span className="text-[11.5px] text-muted-foreground">even</span>
        <span><span className="text-[12.5px] text-muted-foreground">{nickname(G.home.name)}</span> <b className={`${DISPLAY} tabular text-[28px] font-black text-home`}>{pct0(hwin)}</b></span>
      </div>

      <div className={`${DISPLAY} mt-4 text-base font-extrabold uppercase tracking-[0.03em]`}>Wins by how many</div>
      <svg viewBox={`0 0 ${W} 210`} role="img" className="mt-1 block h-auto max-h-[180px] w-full text-[12.5px]"
        aria-label={`Chance of each final margin on these shots: ${m.map((v, i) => `${label(i - M)} ${pct0(v)}`).join(", ")}. ${live ? "It stands" : "It finished"} ${label(actual)}.`}>
        <line x1={0} x2={W} y1={base} y2={base} stroke="var(--foreground)" />
        {m.map((v, i) => {
          const d = i - M, hgt = max ? (v / max) * (base - top) : 0, on = d === actual;
          const fill = d < 0 ? "var(--away)" : d > 0 ? "var(--home)" : "var(--muted-foreground)";
          return (
            <g key={d}>
              <title>{`${label(d)}: ${(v * 100).toFixed(1)}%`}</title>
              <rect x={x(i)} y={base - hgt} width={bw} height={hgt} fill={fill} opacity={on || d === 0 ? 1 : 0.78} />
              {on && <rect x={x(i) - 2} y={base - hgt - 2} width={bw + 4} height={hgt + 2} fill="none" stroke="var(--foreground)" strokeWidth={2} />}
              <text x={x(i) + bw / 2} y={base - hgt - 7} textAnchor="middle" fontWeight={600} fill="var(--foreground)">{v >= 0.005 ? pct0(v) : ""}</text>
              <text x={x(i) + bw / 2} y={base + 17} textAnchor="middle" fontWeight={on ? 700 : 400} fill={on ? "var(--foreground)" : "var(--muted-foreground)"}>
                {d === 0 ? "Tie" : `${Math.abs(d)}${Math.abs(d) === M ? "+" : ""}`}{on ? " ◂" : ""}
              </text>
            </g>
          );
        })}
        <text x={0} y={206} fontSize={12} fontWeight={600} fill="var(--away)">← {G.away.abbrev} WINS BY</text>
        <text x={W} y={206} fontSize={12} fontWeight={600} fill="var(--home)" textAnchor="end">{G.home.abbrev} WINS BY →</text>
      </svg>
    </div>
  );
}

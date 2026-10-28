import Link from "next/link";
import { boxScores, playersFile, seasonGames, teamsFile } from "@/lib/data";
import { longDate } from "@/lib/format";
import { winnerChance } from "@/lib/deserve";
import { standings } from "@/lib/season";
import { nickname, teamName } from "@/lib/teams";
import { gameColors } from "@/lib/team-colors";
import type { GameSummary } from "@/lib/types";

// The home page's lead, picked from the numbers each build: the night's
// story (its biggest upset on the shots, or else its most one-sided game)
// and a few notes on who the shots say is better or worse than the table.

const pct0 = (v: number) => `${Math.round(v * 100)}%`;
/** "a" or "an" before a percentage, by how it's said: an 8%, an 18%, an 80%. */
const article = (v: number) => { const n = Math.round(v * 100); return n === 8 || n === 11 || n === 18 || (n >= 80 && n < 90) ? "an" : "a"; };
const DISPLAY = "font-[family-name:var(--font-display)]";
const KICKER = "text-xs font-bold uppercase tracking-[0.14em] text-muted-foreground";

/** The night's story: the win the shots gave the winner the least chance of,
 *  if any was under 40%; otherwise the game the shots called most clearly. */
function story(games: GameSummary[]) {
  const scored = games.filter(g => g.dw != null && g.hs !== g.as).map(g => ({ g, w: winnerChance(g.hs, g.as, g.dw)! }));
  if (!scored.length) return null;
  const upset = scored.reduce((a, b) => (b.w < a.w ? b : a));
  return upset.w < 0.4 ? { ...upset, upset: true } : { ...scored.reduce((a, b) => (b.w > a.w ? b : a)), upset: false };
}

export function HomeLead({ season, skip }: { season: number; skip?: string }) {
  const games = boxScores(season).filter(g => g.type === 2 || g.type === 3);
  const last = games.find(g => g.date !== skip)?.date;
  const night = last ? games.filter(g => g.date === last) : [];
  const s = story(night);

  const table = standings(teamsFile(season).regular, seasonGames(season), "regular").filter(t => t.gp >= 5 && t.xpts != null);
  const over = table.length ? table.reduce((a, b) => (b.pts - b.xpts! > a.pts - a.xpts! ? b : a)) : null;
  const under = table.length ? table.reduce((a, b) => (b.xpts! - b.pts > a.xpts! - a.pts ? b : a)) : null;
  const shooters = playersFile(season).regular.skaters.filter(p => p.gax_exp != null && p.att >= 25);
  const hot = shooters.length ? shooters.reduce((a, b) => (b.gax - b.gax_exp! > a.gax - a.gax_exp! ? b : a)) : null;
  if (!s && !over) return null;

  const notes: { href: string; head: string; body: string }[] = [];
  if (over && over.pts - over.xpts! >= 2) notes.push({
    href: `/team/${season}/${over.team}`, head: `${teamName(over.team)}: ahead of their chances`,
    body: `${over.pts} points; their shots earned ${over.xpts!.toFixed(1)}. Finishing or goaltending is carrying them.`,
  });
  if (under && under.xpts! - under.pts >= 2) notes.push({
    href: `/team/${season}/${under.team}`, head: `${teamName(under.team)}: better than their record`,
    body: `${under.pts} points; their shots earned ${under.xpts!.toFixed(1)}. The table is underselling them.`,
  });
  if (hot && hot.gax - hot.gax_exp! >= 2) notes.push({
    href: `/player/${hot.id}`, head: `${hot.name}: finishing above his norm`,
    body: `${hot.g} goals on ${hot.ixg.toFixed(1)} xG, ${(hot.gax - hot.gax_exp!).toFixed(1)} more than even his history says to expect.`,
  });

  return (
    <section aria-labelledby="lead-h" className="mb-8 grid items-start gap-x-12 gap-y-6 border-b border-border pb-8 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
      <h2 id="lead-h" className="sr-only">Last night and this season</h2>
      {s && (() => {
        const { g, w } = s, homeWon = g.hs > g.as;
        const [win, lose] = homeWon ? [g.home, g.away] : [g.away, g.home];
        const [ws, ls] = homeWon ? [g.hs, g.as] : [g.as, g.hs];
        const head = s.upset
          ? `The ${nickname(teamName(win))} beat the ${nickname(teamName(lose))} ${ws}–${ls} with ${article(w)} ${pct0(w)} chance`
          : `The ${nickname(teamName(win))} earned it: ${ws}–${ls} over the ${nickname(teamName(lose))}, ${pct0(w)} on the shots`;
        return (
          <Link href={`/game/${g.id}`} className="group block" style={gameColors(g.away, g.home)}>
            <div className={KICKER}>{s.upset ? "Last night's upset" : "Last night's clearest win"} · {longDate(g.date)}</div>
            <div className={`${DISPLAY} mt-2 text-[clamp(26px,3.2vw,36px)] font-extrabold uppercase leading-[1.05] tracking-[0.01em] group-hover:underline`}>{head}</div>
            <div className="mt-4 flex h-3" aria-hidden="true">
              <i className="block bg-away" style={{ width: `${(1 - g.dw!) * 100}%` }} />
              <i className="block bg-home" style={{ width: `${g.dw! * 100}%` }} />
            </div>
            <div className="mt-1.5 flex justify-between text-[13px]">
              <span><b className="font-semibold text-away">{g.away} {pct0(1 - g.dw!)}</b> <span className="text-muted-foreground">deserve to win</span></span>
              <span className="font-semibold text-home">{pct0(g.dw!)} {g.home}</span>
            </div>
            <div className="mt-3 text-sm font-semibold text-foreground">Open the game sheet →</div>
          </Link>
        );
      })()}
      {notes.length > 0 && (
        <div>
          <div className={KICKER}>What the shots say this season</div>
          <ul className="mt-2 divide-y divide-border">
            {notes.map(n => (
              <li key={n.href}>
                <Link href={n.href} className="group block py-2.5">
                  <div className="text-[15px] font-semibold group-hover:underline">{n.head}</div>
                  <div className="text-[13.5px] text-muted-foreground">{n.body}</div>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

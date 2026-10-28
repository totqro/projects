import Link from "next/link";
import { cn } from "@/lib/utils";
import { longDate, pct, seasonLabel, share, signed } from "@/lib/format";
import { boxScores, seasonIndex, seasons, teamsFile } from "@/lib/data";
import { teamGames } from "@/lib/season";
import { teamName } from "@/lib/teams";
import { gameColors } from "@/lib/team-colors";
import type { TeamSeason, TonightGame } from "@/lib/types";
import { Card, CardContent } from "@/components/ui/card";
import { Note, Section } from "@/components/site/section";
import { TeamLogo } from "@/components/site/team-logo";
import { BackLink } from "@/components/site/trail";
import { MiniBox } from "@/components/games/games-view";

// The page for one of tonight's games before it has any shots: how the two
// teams have played this season, side by side, and their earlier meetings.
// Once the game is on, the next update swaps in the sheet so far.

const LAST = 10;

const startTime = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: "America/New_York" }) + " ET";

interface Side {
  ab: string;
  row: TeamSeason | undefined;
  /** Last LAST games: record and 5v5 xG share. */
  rec: string;
  xg5: number | null;
}

function side(ab: string, season: number, phase: "regular" | "playoff"): Side {
  const tf = teamsFile(season);
  const row = tf[phase].find(t => t.team === ab) ?? tf.regular.find(t => t.team === ab);
  const last = teamGames(seasonIndex(season).games, ab, row && tf[phase].includes(row) ? phase : "regular").slice(-LAST);
  const n = (r: string) => last.filter(g => g.res === r).length;
  return {
    ab, row,
    rec: last.length ? `${n("W")}-${n("L")}-${n("OTL")}` : "–",
    xg5: share(last.reduce((s, g) => s + g.xgf5, 0), last.reduce((s, g) => s + g.xga5, 0)),
  };
}

/** One line of the comparison: each team's number, the better one marked. */
interface Line { label: string; get: (s: Side) => number | null | undefined; show: (v: number) => string; low?: boolean }
const LINES: Line[] = [
  { label: "Points %", get: s => (s.row?.gp ? s.row.pts / (2 * s.row.gp) : null), show: v => pct(v, 1) },
  { label: "Goal differential", get: s => (s.row ? s.row.gf - s.row.ga : null), show: v => signed(v, 0) },
  { label: "5v5 xG share", get: s => s.row?.["5v5"].xgf_pct, show: v => pct(v, 1) },
  { label: "5v5 xGF/60", get: s => s.row?.["5v5"].xgf60, show: v => v.toFixed(2) },
  { label: "5v5 xGA/60", get: s => s.row?.["5v5"].xga60, show: v => v.toFixed(2), low: true },
  { label: "Power play xGF/60", get: s => s.row?.pp.xgf60, show: v => v.toFixed(2) },
  { label: "Penalty kill xGA/60", get: s => s.row?.pk.xga60, show: v => v.toFixed(2), low: true },
  { label: "Goalies' GSAx", get: s => s.row?.gsax_team, show: v => signed(v, 1) },
  { label: `Last ${LAST}: 5v5 xG share`, get: s => s.xg5, show: v => pct(v, 1) },
];

function Compare({ a, h }: { a: Side; h: Side }) {
  return (
    <table className="tabular w-full text-sm">
      <thead>
        <tr className="border-b border-border text-xs text-muted-foreground">
          <th className="w-1/3 pb-2 text-left font-normal text-away">{a.ab}</th>
          <th className="pb-2 font-normal">This season</th>
          <th className="w-1/3 pb-2 text-right font-normal text-home">{h.ab}</th>
        </tr>
      </thead>
      <tbody>
        <tr className="border-b border-border/60">
          <td className="py-2 text-left">{a.rec}</td>
          <td className="py-2 text-center text-muted-foreground">Last {LAST} (W-L-OTL)</td>
          <td className="py-2 text-right">{h.rec}</td>
        </tr>
        {LINES.map(l => {
          const va = l.get(a), vh = l.get(h);
          const both = va != null && vh != null && va !== vh;
          const aBetter = both && (l.low ? va! < vh! : va! > vh!), hBetter = both && !aBetter;
          return (
            <tr key={l.label} className="border-b border-border/60 last:border-0">
              <td className={cn("py-2 text-left", aBetter ? "font-semibold text-foreground" : "text-secondary-foreground")}>{va == null ? "–" : l.show(va)}</td>
              <td className="py-2 text-center text-muted-foreground">{l.label}</td>
              <td className={cn("py-2 text-right", hBetter ? "font-semibold text-foreground" : "text-secondary-foreground")}>{vh == null ? "–" : l.show(vh)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function TeamHead({ ab, season, record, where, right }: { ab: string; season: number; record: string | null; where: string; right?: boolean }) {
  return (
    <Link href={`/team/${season}/${ab}`} className={cn("group flex items-center gap-3 rounded-lg", right ? "justify-end justify-self-end text-right" : "justify-self-start")}>
      {!right && <TeamLogo team={ab} size={64} className="max-sm:hidden" />}
      <div>
        <div className={cn("font-[family-name:var(--font-display)] text-[clamp(22px,3vw,30px)] font-bold tracking-[-0.02em] underline-offset-4 group-hover:underline", right ? "text-home" : "text-away")}>{ab}</div>
        <div className="text-xs text-muted-foreground">{teamName(ab)}, {where}{record ? ` · ${record}` : ""}</div>
      </div>
      {right && <TeamLogo team={ab} size={64} className="max-sm:hidden" />}
    </Link>
  );
}
export function GamePreview({ g, date }: { g: TonightGame; date: string }) {
  const season = Math.floor(g.id / 1e6);
  const published = seasons().includes(season);
  const phase = g.type === 3 ? "playoff" : "regular";
  const a = published ? side(g.away.abbrev, season, phase) : null;
  const h = published ? side(g.home.abbrev, season, phase) : null;
  const meetings = published
    ? boxScores(season).filter(x => (x.home === g.home.abbrev && x.away === g.away.abbrev) || (x.home === g.away.abbrev && x.away === g.home.abbrev))
    : [];
  const started = g.state === "live" || g.state === "final";
  return (
    <div style={gameColors(g.away.abbrev, g.home.abbrev)}>
      <BackLink key={g.id} href={`/games/${season}`} label="All games" className="mb-4 inline-block max-w-full truncate align-top text-sm text-muted-foreground hover:text-foreground" />
      <h1 className="sr-only">{teamName(g.away.abbrev)} at {teamName(g.home.abbrev)}, preview</h1>
      <Card className="slot-plate mb-6">
        <CardContent className="p-5">
          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
            <TeamHead ab={g.away.abbrev} season={season} record={g.away.record} where="away" />
            <div className="text-center">
              <div className="tabular font-[family-name:var(--font-display)] text-[clamp(26px,4vw,40px)] font-bold leading-none tracking-[-0.02em]">
                {started ? <>{g.away.score ?? 0}<span className="mx-2 text-muted-foreground">&ndash;</span>{g.home.score ?? 0}</> : startTime(g.start)}
              </div>
              <div className="mt-1.5 text-xs text-muted-foreground">
                <span className="font-medium text-brand">{g.state === "off" ? "Postponed" : g.state === "live" ? "In progress" : g.state === "final" ? "Final" : "Preview"}</span>, {longDate(date)}
              </div>
            </div>
            <TeamHead ab={g.home.abbrev} season={season} record={g.home.record} where="home" right />
          </div>
        </CardContent>
      </Card>
      {started && (
        <Note className="mb-6 max-w-3xl">The game is on: its sheet, with the expected goals so far, comes with the next update, about every 20 minutes.</Note>
      )}
      {a && h ? (
        <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
          <Section title={`How they've played, ${seasonLabel(season)}`}>
            <Compare a={a} h={h} />
            <Note className="mt-3 text-xs">The better number of each pair is in bold. Rates are per 60 minutes in that situation; GSAx is goals saved above expected by the team&apos;s goalies.</Note>
          </Section>
          <Section title="Earlier meetings">
            {meetings.length
              ? <div className="grid gap-3 sm:grid-cols-2">{meetings.map(x => <MiniBox key={x.id} x={x} />)}</div>
              : <Note>First meeting of the season.</Note>}
          </Section>
        </div>
      ) : (
        <Note>Season numbers appear after the season&apos;s first games.</Note>
      )}
    </div>
  );
}

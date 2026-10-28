import type { Metadata } from "next";
import Link from "next/link";
import { linesFile, playerGames, playersFile, seasons, shotsByShooter } from "@/lib/data";
import { f1, f2, fmtDate, pct, seasonLabel, share, sv, toi } from "@/lib/format";
import { posLabel, teamName } from "@/lib/teams";
import type { GamePlayer, TeamUnits } from "@/lib/types";
import { PageHead } from "@/components/site/page-head";
import { TeamLogo } from "@/components/site/team-logo";
import { Note, Section, Tile } from "@/components/site/section";
import { PlayerLog } from "@/components/players/player-log";
import { PlayerTrend } from "@/components/players/player-trend";
import { Signed } from "@/components/tables/sortable";
import { PlayerShotMap, type PlayerShot } from "@/components/players/player-shots";
import { PlayerSeasons } from "@/components/players/player-seasons";
import { WowyTable } from "@/components/teams/lines-view";
import { relXg } from "@/lib/season";

export const dynamicParams = false;
export const generateStaticParams = () => [...playerGames().keys()].map(id => ({ id: String(id) }));

type Props = { params: Promise<{ id: string }> };

function who(id: number) {
  const log = playerGames().get(id) ?? [];
  const last = log[log.length - 1];
  return { log, name: last?.line.name ?? "Unknown", pos: last?.line.pos ?? "", team: last?.team ?? "" };
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { name, team } = who(+(await params).id);
  return { title: `${name}, ${teamName(team)}`, description: `${name}'s expected goals, game by game.` };
}

/** Only the keys the game log shows, so each page stays small (the name and
 *  team would repeat on every row). */
const SK_KEYS = ["toi_all", "g", "a", "ixg", "att", "xgf", "xga", "gf", "ga", "xgf5", "xga5", "gf5", "ga5"] as const;
const GK_KEYS = ["toi_all", "sa", "ga_", "xga_"] as const;
function trim(line: GamePlayer, goalie: boolean): GamePlayer {
  const out = {} as GamePlayer;
  for (const k of goalie ? GK_KEYS : SK_KEYS) if (line[k] != null) out[k] = line[k];
  return out;
}

/** A season's line from players.json, regular season first. */
function seasonLines(id: number) {
  return seasons().flatMap(s => (["regular", "playoff"] as const).flatMap(ph => {
    const P = playersFile(s)[ph];
    const sk = P.skaters.find(p => p.id === id), gk = P.goalies.find(p => p.id === id);
    return sk || gk ? [{ season: s, phase: ph, sk, gk }] : [];
  }));
}

/** His unblocked shots in one season's games, compact for the shot map.
 *  Every game he played is listed, shots or not, so the map's last-N-games
 *  windows count games played. */
function seasonShots(id: number, log: { id: number; date: string; opp: string; home: boolean }[]) {
  const mine = shotsByShooter().get(id) ?? [];
  const games: string[] = [], shots: PlayerShot[] = [];
  for (const g of log) {
    games.push(`${fmtDate(g.date)} ${g.home ? "vs" : "@"} ${g.opp}`);
    for (const s of mine.filter(s => s.gid === g.id))
      shots.push([Math.round(s.x * 10) / 10, Math.round(s.y * 10) / 10, Math.round(s.xg * 1000) / 1000,
        s.ev === "GOAL" ? "G" : s.ev === "SHOT" ? "S" : "M", s.type, s.p, s.t, games.length - 1]);
  }
  return { games, shots };
}

/** Only the rows WOWY needs for one player: his pairs and his teammates' totals. */
function wowyUnits(u: TeamUnits | undefined, id: number): TeamUnits | null {
  if (!u || !u.solo.some(r => r[0][0] === id)) return null;
  const pairs = u.pairs.filter(r => r[0].includes(id));
  const ids = new Set(pairs.flatMap(r => r[0]));
  return {
    players: Object.fromEntries(Object.entries(u.players).filter(([k]) => ids.has(+k))),
    solo: u.solo.filter(r => ids.has(r[0][0])), fwd: [], def: [], pairs,
  };
}

export default async function Player({ params }: Props) {
  const id = +(await params).id;
  const { log, name, pos, team } = who(id);
  const goalie = pos === "G";
  const lines = seasonLines(id);
  const seasonsPlayed = seasons().filter(s => log.some(g => g.season === s));

  /** Everything below the header for one season: the tiles, shot map, WOWY and game log. */
  function seasonBlock(s: number) {
    const cur = lines.find(l => l.season === s);
    const rows = log.filter(g => g.season === s);
    const logRows = rows.map(r => ({ ...r, line: trim(r.line, goalie) }));
    const trendRows = logRows.filter(r => r.type === (cur?.phase === "playoff" ? 3 : 2));
    const { games: shotGames, shots } = !goalie && cur ? seasonShots(id, rows) : { games: [], shots: [] };
    const wowy = !goalie && cur ? wowyUnits(linesFile(cur.season)?.[cur.phase][cur.sk?.team ?? team], id) : null;
    const rel = cur?.sk ? relXg(cur.sk) : null;
    return (
      <>
        {cur && (
          <Section title={`${seasonLabel(cur.season)}${cur.phase === "playoff" ? " playoffs" : ""}`} className="mb-8">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-[repeat(auto-fit,minmax(128px,1fr))]">
              {cur.sk && <>
                <Tile label="Games">{cur.sk.gp}</Tile>
                <Tile label="Goals, assists">{cur.sk.g}&ndash;{cur.sk.a}</Tile>
                <Tile label="Points"><span className="brand-text">{cur.sk.pts}</span></Tile>
                <Tile label="ixG">{f1(cur.sk.ixg)}</Tile>
                <Tile label="Goals above expected"><Signed v={cur.sk.gax} /></Tile>
                <Tile label="5v5 xG share">{pct(cur.sk.xgf_pct5)}</Tile>
                <Tile label="5v5 goal share">{pct(share(cur.sk.gf5, cur.sk.ga5))}</Tile>
                <Tile label="TOI per game">{toi(cur.sk.toi / cur.sk.gp)}</Tile>
                {rel != null && <>
                  <Tile label="5v5 xG share, off ice">{pct(share(cur.sk.xgf5_off ?? 0, cur.sk.xga5_off ?? 0))}</Tile>
                  <Tile label="Rel 5v5 xG%"><Signed v={rel * 100} /></Tile>
                </>}
              </>}
              {cur.gk && <>
                <Tile label="Games">{cur.gk.gp}</Tile>
                <Tile label="GSAx"><Signed v={cur.gk.gsax} /></Tile>
                <Tile label="Save %">{sv(cur.gk.sv_pct)}</Tile>
                <Tile label="Expected save %">{sv(cur.gk.xsv_pct)}</Tile>
                <Tile label="GSAx per 60"><Signed v={cur.gk.gsax60} d={2} /></Tile>
                <Tile label="xGA">{f2(cur.gk.xga)}</Tile>
                <Tile label="Goals allowed">{cur.gk.ga}</Tile>
              </>}
            </div>
          </Section>
        )}

        {cur && (shots.length > 0 || wowy) && (
          <div className="mb-8 grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)]">
            {shots.length > 0 && (
              <Section title={`Shots, ${seasonLabel(cur.season)}`}>
                <PlayerShotMap shots={shots} games={shotGames} />
              </Section>
            )}
            {wowy && (
              <Section title="With or without you, 5v5">
                <WowyTable units={wowy} playerId={id} minSecs={120} csvName={`${name.toLowerCase().replace(/[^a-z]+/g, "-")}-${cur.season}`} />
                <Note className="mt-2 text-xs">{cur.season ? seasonLabel(cur.season) : ""}{cur.phase === "playoff" ? " playoffs" : ""}, teammates with at least two minutes together. Rel xG% is his 5v5 xG share minus his team&apos;s with him on the bench.</Note>
              </Section>
            )}
          </div>
        )}

        {trendRows.length >= 3 && (
          <Section title={`Game by game${cur?.phase === "playoff" ? ", playoffs" : ""}`} className="mb-8">
            <PlayerTrend goalie={goalie} rows={trendRows} />
          </Section>
        )}

        <Section title={`${seasonLabel(s)} game log`}>
          <PlayerLog goalie={goalie} rows={logRows} />
        </Section>
      </>
    );
  }
  const blocks = seasonsPlayed.map(s => ({ season: s, label: seasonLabel(s), node: seasonBlock(s) }));

  return (
    <>
      <PageHead title={name} sub={<span className="inline-flex items-center gap-2">{team && <TeamLogo team={team} size={28} />}{posLabel(pos)}, <Link href={`/team/${log[log.length - 1]?.season}/${team}`} className="hover:underline">{teamName(team)}</Link></span>}>
        <Link href={`/compare?p=${id}`} className="rounded-md border border-border px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground">Compare</Link>
      </PageHead>

      <PlayerSeasons blocks={blocks} />
    </>
  );
}

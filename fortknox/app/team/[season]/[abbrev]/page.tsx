import type { Metadata } from "next";
import Link from "next/link";
import { seasonIndex, sheet, teamSeasons, teamsFile } from "@/lib/data";
import { ordinal, seasonLabel } from "@/lib/format";
import { standings, teamGames } from "@/lib/season";
import { TEAMS, teamName } from "@/lib/teams";
import { PageHead } from "@/components/site/page-head";
import { TeamLogo } from "@/components/site/team-logo";
import { TeamView, type Line, type LogGame, type TeamData } from "@/components/teams/team-view";
import type { TeamGame } from "@/lib/season";

export const dynamicParams = false;
export const generateStaticParams = () => teamSeasons().map(({ season, team }) => ({ season: String(season), abbrev: team }));

type Props = { params: Promise<{ season: string; abbrev: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { season, abbrev } = await params;
  return { title: `${teamName(abbrev)}, ${seasonLabel(+season)}` };
}

export default async function Team({ params }: Props) {
  const { season: s, abbrev: ab } = await params;
  const season = +s;
  const games = seasonIndex(season).games, T = teamsFile(season);
  const std = standings(T.regular, games, "regular");
  const me = std.find(x => x.team === ab);
  const meta = TEAMS[ab];
  const rankIn = (k: 1 | 2) => std.filter(x => TEAMS[x.team]?.[k] === meta?.[k]).findIndex(x => x.team === ab) + 1;
  const standingLine = me && meta
    ? `${me.w}-${me.l}-${me.otl}, ${me.pts} points. ${ordinal(rankIn(2))} in the ${meta[2]}, ${ordinal(rankIn(1))} in the ${meta[1]}, ${ordinal(me.lg)} in the league.`
    : null;
  // The index has no 5v5 goals per game, so count them from each sheet's shots.
  const with5 = (g: TeamGame): LogGame => {
    const goals = sheet(g.id).shots.filter(x => x.ev === "GOAL" && x.sit === "EV_5v5");
    return { ...g, gf5: goals.filter(x => x.team === ab).length, ga5: goals.filter(x => x.team !== ab).length };
  };
  const tg = { regular: teamGames(games, ab, "regular").map(with5), playoff: teamGames(games, ab, "playoff").map(with5) };
  // Each game's lines for this team's players, trimmed to what the page sums.
  const lines: Line[] = [...tg.regular, ...tg.playoff].flatMap(g =>
    sheet(g.id).players.filter(p => p.team === ab && (p.toi_all || p.att || p.sa)).map(p => ({
      gid: g.id, id: p.id, name: p.name, pos: p.pos,
      toi_all: p.toi_all ?? 0, toi_5v5: p.toi_5v5 ?? 0, g: p.g ?? 0, a: p.a ?? 0, ixg: p.ixg ?? 0, att: p.att ?? 0,
      xgf: p.xgf ?? 0, xga: p.xga ?? 0, xgf5: p.xgf5 ?? 0, xga5: p.xga5 ?? 0,
      gf: p.gf ?? 0, ga: p.ga ?? 0, gf5: p.gf5 ?? 0, ga5: p.ga5 ?? 0, sa: p.sa ?? 0, ga_: p.ga_ ?? 0, xga_: p.xga_ ?? 0,
    })));
  const d: TeamData = { season, team: ab, name: teamName(ab), standingLine, games: tg, lines };
  return (
    <>
      <Link href={`/teams/${season}`} className="mb-4 inline-block text-sm text-muted-foreground hover:text-foreground">&larr; All teams</Link>
      <PageHead title={<span className="inline-flex items-center gap-3"><TeamLogo team={ab} size={56} />{teamName(ab)}</span>} sub={standingLine ?? seasonLabel(season)} />
      <TeamView d={d} />
    </>
  );
}

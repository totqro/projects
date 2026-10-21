import type { Metadata } from "next";
import { playersFile, seasonIndex, seasons, teamsFile } from "@/lib/data";
import { seasonLabel } from "@/lib/format";
import { standings } from "@/lib/season";
import type { Phase } from "@/lib/types";
import { PageHead } from "@/components/site/page-head";
import { RegressionView, type RegPhase } from "@/components/regression/regression-view";

export const dynamicParams = false;
export const generateStaticParams = () => seasons().map(s => ({ season: String(s) }));

type Props = { params: Promise<{ season: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const s = seasonLabel(+(await params).season);
  return { title: `${s} regression watch`, description: `Which NHL teams, shooters and goalies are ahead of or behind their expected goals in ${s}.` };
}

/** One phase, trimmed to the columns the page shows. */
function phaseData(season: number, ph: Phase): RegPhase {
  const P = playersFile(season)[ph];
  return {
    teams: standings(teamsFile(season)[ph], seasonIndex(season).games, ph)
      .map(({ team, gp, pts, xgf, xga, gf_x, ga_x, gax, gsax }) => ({ team, gp, pts, xgf, xga, gf_x, ga_x, gax, gsax })),
    skaters: P.skaters.map(({ id, name, team, pos, gp, toi5, g, ixg, gax, att, sog, xgf5, xga5, gf5, ga5 }) =>
      ({ id, name, team, pos, gp, toi5, g, ixg, gax, att, sog, xgf5, xga5, gf5, ga5 })),
    goalies: P.goalies.map(({ id, name, team, gp, toi, sa, ga, xga, gsax, sv_pct, xsv_pct }) =>
      ({ id, name, team, gp, toi, sa, ga, xga, gsax, sv_pct, xsv_pct })),
  };
}

export default async function Regression({ params }: Props) {
  const season = +(await params).season;
  return (
    <>
      <PageHead title="Regression watch" sub={`Who is ahead of or behind their chances in ${seasonLabel(season)}. Shooting and save percentages drift back toward normal; expected goals hold up, so the gap between the two is the part of a record most likely to fade.`} />
      <RegressionView season={season} data={{ regular: phaseData(season, "regular"), playoff: phaseData(season, "playoff") }} />
    </>
  );
}

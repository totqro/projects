import type { Metadata } from "next";
import { seasons } from "@/lib/data";
import { fmtDate, seasonLabel } from "@/lib/format";
import { projections } from "@/lib/projections";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHead } from "@/components/site/page-head";
import { Note, Section, Tile } from "@/components/site/section";
import { PlayoffsView } from "@/components/playoffs/playoffs-view";
import { OddsCalibrationChart, type OddsBin } from "@/components/charts/odds-calibration";
import backtestFile from "../backtest.json";

// pipeline/fit_projections.py; refit each summer.
interface Score { n: number; brier: number; log_loss: number; pts_mae: number; pts_cover80?: number }
const backtest = backtestFile as unknown as {
  seasons: number[]; checkpoints: string[]; sigma: number; overall: Score; flip: Score; bins: OddsBin[];
  by_checkpoint: (Score & { cp: string; flip_brier: number; flip_pts_mae: number })[];
  core4_compare?: Record<string, { n: number; core4_highslot: number; core4_moneypuck: number }>;
};

export const dynamicParams = false;
export const generateStaticParams = () => seasons().map(s => ({ season: String(s) }));

type Props = { params: Promise<{ season: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const s = seasonLabel(+(await params).season);
  return { title: `${s} playoff odds`, description: `Projected final standings and playoff odds for every NHL team in ${s}, from 10,000 simulated seasons.` };
}

const H3 = ({ children }: { children: React.ReactNode }) => <h3 className="mb-2 mt-6 text-base font-semibold tracking-[-0.015em]">{children}</h3>;
const P = ({ children }: { children: React.ReactNode }) => <p className="mb-3 max-w-[72ch] text-[15px] leading-relaxed text-secondary-foreground [&_b]:font-semibold [&_b]:text-foreground">{children}</p>;
const head = "h-9 px-3 text-xs font-medium normal-case tracking-normal";
const n3 = (v: number) => v.toFixed(3).replace(/^0/, "");

export default async function Playoffs({ params }: Props) {
  const season = +(await params).season;
  const p = projections(season);
  const bt = backtest;
  const first = seasonLabel(bt.seasons[0]), last = seasonLabel(bt.seasons[bt.seasons.length - 1]);
  const beatAll = bt.by_checkpoint.every(r => r.brier < r.flip_brier);
  const cmp = bt.core4_compare ? Object.entries(bt.core4_compare) : [];
  return (
    <>
      <PageHead title="Playoff odds"
        sub={p
          ? `The rest of ${seasonLabel(season)} played out ${p.sims.toLocaleString("en-US")} times, from every result through ${p.as_of ? fmtDate(p.as_of) : "opening night"}.`
          : `No projection for ${seasonLabel(season)}: odds are published only for a regular season in progress.`} />

      {p && (
        <>
          <div className="mb-8 grid max-w-3xl grid-cols-2 gap-2 sm:grid-cols-4">
            <Tile label="Games played">{p.games_played.toLocaleString("en-US")}</Tile>
            <Tile label="Games left">{p.games_left.toLocaleString("en-US")}</Tile>
            <Tile label="Seasons simulated">{p.sims.toLocaleString("en-US")}</Tile>
            <Tile label="Results through">{p.as_of ? fmtDate(p.as_of) : "–"}</Tile>
          </div>
          <PlayoffsView season={season} teams={p.teams} />
          <Note className="mt-3 max-w-[72ch]">
            The line under a team marks the last playoff place: eighth in the conference, or third in the division. Teams are ordered by their playoff odds. Ties in points are broken by regulation wins, regulation and overtime wins, wins, then goal differential; the NHL&apos;s head-to-head step is left out.
          </Note>
        </>
      )}

      <Section title="How it works" className="mt-12">
        <P>Every game left on the NHL schedule gets a win probability, and then the season is played out {p ? p.sims.toLocaleString("en-US") : "10,000"} times. Each simulated game can go to overtime, which hands the loser a point, and finished seasons are ranked the way the league ranks them: top three in each division plus two wild cards per conference.</P>
        <H3>The win probability</H3>
        <P>It is <b>core4</b>, the four-number model a search over 52 candidate variables kept. The four numbers are the <b>Elo difference</b> between the two teams, from every result since 2014-15; their <b>5-on-5 xG differential per game</b> this season, from this site&apos;s own expected goals; and whether <b>either team played the night before</b>. Home ice comes from the intercept. Until both teams have five games, xG is too noisy, so Elo stands in alone.</P>
        {cmp.length > 0 && (
          <P>The original core4 runs on MoneyPuck&apos;s xG. Refit on High Slot&apos;s xG, it predicts single games just as well: on every game once both teams had five, its log loss was {cmp.map(([s, c], i) => <span key={s}>{i ? " and " : ""}{c.core4_highslot.toFixed(4)} against {c.core4_moneypuck.toFixed(4)} in {seasonLabel(+s)}</span>)}, each season predicted by a model fit only on the seasons before it.</P>
        )}
        <H3>Overtime and luck</H3>
        <P>{p ? `${Math.round(p.model.ot.rate * 100)}%` : "About 22%"} of games go past regulation, as they have since 3-on-3 overtime began. A favourite keeps only about {p ? Math.round(p.model.ot.k * 100) : 37}% of its edge in overtime and the shootout. A team&apos;s rating after a few weeks is an estimate, so every simulated season also nudges each team up or down by a random amount. The back-test set how big that nudge is: without it the ranges come out too narrow.</P>
      </Section>

      <Section title="Does it work?" className="mt-12">
        <P>We projected {first} to {last} (skipping the two shortened COVID seasons) from five dates in each: {bt.checkpoints.join(", ")}. Every season was projected by a model fit on the others. Below, each team-season&apos;s odds are grouped into bands and set against the share that actually made it.</P>
        <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <OddsCalibrationChart bins={bt.bins} />
          <div className="min-w-0 overflow-x-auto">
            <Table className="tabular text-[13px]">
              <TableHeader className="bg-transparent">
                <TableRow className="hover:bg-transparent">
                  <TableHead className={head}>From</TableHead>
                  <TableHead className={`${head} text-right`}>Brier</TableHead>
                  <TableHead className={`${head} text-right`}>Coin flips</TableHead>
                  <TableHead className={`${head} text-right`}>Points off</TableHead>
                  <TableHead className={`${head} text-right`}>In 80% range</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {bt.by_checkpoint.map(r => (
                  <TableRow key={r.cp}>
                    <TableCell className="px-3">{r.cp}</TableCell>
                    <TableCell className="px-3 text-right font-semibold">{n3(r.brier)}</TableCell>
                    <TableCell className="px-3 text-right text-muted-foreground">{n3(r.flip_brier)}</TableCell>
                    <TableCell className="px-3 text-right">{r.pts_mae.toFixed(1)}</TableCell>
                    <TableCell className="px-3 text-right">{r.pts_cover80 != null ? `${Math.round(r.pts_cover80 * 100)}%` : "–"}</TableCell>
                  </TableRow>
                ))}
                <TableRow className="font-semibold">
                  <TableCell className="px-3">All</TableCell>
                  <TableCell className="px-3 text-right">{n3(bt.overall.brier)}</TableCell>
                  <TableCell className="px-3 text-right text-muted-foreground">{n3(bt.flip.brier)}</TableCell>
                  <TableCell className="px-3 text-right">{bt.overall.pts_mae.toFixed(1)}</TableCell>
                  <TableCell className="px-3 text-right">{bt.overall.pts_cover80 != null ? `${Math.round(bt.overall.pts_cover80 * 100)}%` : "–"}</TableCell>
                </TableRow>
              </TableBody>
            </Table>
            <Note className="mt-3">
              <b className="font-semibold text-foreground">Brier</b> is the squared miss on playoff odds, so lower is better. <b className="font-semibold text-foreground">Coin flips</b> projects the same standings with every remaining game a coin flip weighted for home ice. <b className="font-semibold text-foreground">Points off</b> is the average miss on final points. <b className="font-semibold text-foreground">In 80% range</b> is how often the final total landed inside the range; it should be about 80%. Across {bt.overall.n.toLocaleString("en-US")} team projections the model {beatAll ? "beat coin flips from every date" : `scored ${n3(bt.overall.brier)} against coin flips' ${n3(bt.flip.brier)}`}.
            </Note>
          </div>
        </div>
      </Section>
    </>
  );
}

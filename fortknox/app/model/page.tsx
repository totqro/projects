import type { Metadata } from "next";
import { currentSeason } from "@/lib/data";
import { modelStats } from "@/lib/model";
import { seasonLabel } from "@/lib/format";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHead } from "@/components/site/page-head";
import { Tile } from "@/components/site/section";
import { CalibrationChart } from "@/components/charts/calibration";
import { ValidationChart, type Validation } from "@/components/charts/validation";
import validationFile from "./validation.json";

// pipeline/fit_validation.py; rerun it after a refit.
const validation = validationFile as Validation;
/** The first game where points % catches 5v5 xG share, past the opening noise. */
const validationCross = validation.n.find((n, i) => n > 10 && validation.r.pts[i]! >= validation.r.xgs5[i]!);

export const metadata: Metadata = { title: "How the xG model works" };

const H3 = ({ children }: { children: React.ReactNode }) => <h2 className="mb-2 mt-7 text-base font-semibold tracking-[-0.015em]">{children}</h2>;
const P = ({ children }: { children: React.ReactNode }) => <p className="mb-3 max-w-[72ch] text-[15px] leading-relaxed text-secondary-foreground [&_b]:font-semibold [&_b]:text-foreground">{children}</p>;

// Measured once with pipeline/train_nhl_xg.py (see pipeline/README.md): the
// evaluation model never saw these seasons.
const EVAL_ROWS = [
  ["2024-25", "0.767", "0.2206", "1.005"],
  ["2025-26", "0.757", "0.2264", "1.062"],
];

// Measured 2026-11-16: the published 2026-27 sheets joined to MoneyPuck's shot
// file (235 games, 99% of unblocked shots matched on game, period, time,
// shooter and event). Neither model had seen these games. Refresh when
// rerun; past seasons don't work as a benchmark (see the note under the table).
const MP_AS_OF = "Nov 16, 2026";
const MP_GAMES = 235;
const MP_ROWS: [string, string, string, string, string, string, string][] = [
  ["All shots", "0.782", "0.2273", "0.972", "0.785", "0.2260", "1.000"],
  ["5 on 5", "0.785", "0.2012", "0.956", "0.790", "0.1994", "1.011"],
  ["Power play", "0.705", "0.3136", "0.997", "0.714", "0.3104", "1.000"],
];

export default function Model() {
  const s = currentSeason();
  const m = modelStats(s);
  const live = [`${seasonLabel(s)} so far (${m.shots.toLocaleString("en-US")} shots)`, m.auc.toFixed(3), m.logLoss.toFixed(4), (m.xg / m.goals).toFixed(3)];
  const head = "h-9 px-3 text-xs font-medium normal-case tracking-normal";
  return (
    <>
      <PageHead title="How the xG model works" />
      <div className="mb-6 grid max-w-3xl grid-cols-1 gap-2 sm:grid-cols-3">
        <Tile label="Trained on">1.13M shots</Tile>
        <Tile label="Training seasons">2015-16 to 2024-25</Tile>
        <Tile label={`${seasonLabel(s)} xG vs goals`}>{m.xg.toFixed(0)} / {m.goals}</Tile>
      </div>
      <Card className="max-w-4xl">
        <CardContent>
          <P>Each unblocked shot gets a probability of becoming a goal, from a gradient-boosted model trained on every NHL shot since 2015-16 and built from the league&apos;s own play-by-play and shift charts, the same feed it scores after each game. A team&apos;s or player&apos;s xG is the sum of those probabilities.</P>
          <H3>What it looks at</H3>
          <P>Mostly <b>the shot itself</b>, meaning its distance, angle, type, whether it came from behind the net, and the shooter&apos;s handedness and wing. It also looks at <b>the play before it</b>, such as what the previous event was, where and how long ago it happened, whether this is a rebound (and off a save, a miss or a block), and how fast the puck moved. On top of that it knows the <b>game state</b> (strength, including a pulled goalie and why, plus score, period and time) and <b>fatigue</b>, which is how long the shooter and both units had been on the ice.</P>
          <H3>What it can&apos;t see</H3>
          <P>The public feed doesn&apos;t log passes or zone entries, so <b>cross-ice feeds and true rushes are invisible</b>. The model uses proxies: seconds since the puck was last outside the zone, since the team won it, and whether the puck crossed the middle. They help a little. Screens, traffic, shot speed and where the shot was aimed aren&apos;t in the data at all.</P>
          <H3>How good it is</H3>
          <P>There are two models. The <b>served model</b> scores every game on this site. It was trained on 2015-16 to 2024-25 and then calibrated on 2025-26. Scoring drifts from one season to the next, so during a season it also adjusts to the games already played: before each game day, the odds at 5v5, on the power play and in other situations are scaled by how goals compare with xG on earlier days. A game&apos;s xG doesn&apos;t change after its date. The <b>evaluation model</b> exists only to measure the served one honestly. It was trained through 2022-23 and calibrated on 2023-24, so it never saw the seasons it&apos;s tested on.</P>
          <Table className="tabular text-[13px]">
            <TableHeader className="bg-transparent">
              <TableRow className="hover:bg-transparent">
                <TableHead className={head}>Season</TableHead>
                <TableHead className={`${head} text-right`}>AUC</TableHead>
                <TableHead className={`${head} text-right`}>Log loss</TableHead>
                <TableHead className={`${head} text-right`}>xG / goals</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow className="hover:bg-transparent"><TableCell colSpan={4} className="px-3 pb-1 pt-3 text-xs font-medium text-muted-foreground">Served model, games it has never seen (updates after every game)</TableCell></TableRow>
              <TableRow>{live.map((v, i) => <TableCell key={i} className={`px-3 py-2 ${i ? "text-right" : ""}`}>{v}</TableCell>)}</TableRow>
              <TableRow className="hover:bg-transparent"><TableCell colSpan={4} className="px-3 pb-1 pt-3 text-xs font-medium text-muted-foreground">Evaluation model, held-out seasons</TableCell></TableRow>
              {EVAL_ROWS.map(([l, auc, ll, r]) => (
                <TableRow key={l}>
                  <TableCell className="px-3 py-2">{l}</TableCell>
                  <TableCell className="px-3 py-2 text-right">{auc}</TableCell>
                  <TableCell className="px-3 py-2 text-right">{ll}</TableCell>
                  <TableCell className="px-3 py-2 text-right">{r}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <div className="mt-4" />
          <P><b>AUC</b> is how well it ranks dangerous shots over safe ones (0.5 is a coin flip). <b>Log loss</b> scores each probability against what happened; lower is better. <b>xG / goals</b> checks whether the totals are right, and 1.00 is perfect. Early in a season the live row moves a lot from week to week.</P>
          <H3>Against MoneyPuck, on the same shots</H3>
          <P>MoneyPuck is the best-known public model and publishes every shot it scores. These are the {MP_GAMES} games of {seasonLabel(s)} in both data sets as of {MP_AS_OF}. Neither model had seen them.</P>
          <Table className="tabular text-[13px]">
            <TableHeader className="bg-transparent">
              <TableRow className="hover:bg-transparent">
                <TableHead className={head} />
                <TableHead colSpan={3} className={`${head} text-center`}>High Slot</TableHead>
                <TableHead colSpan={3} className={`${head} text-center`}>MoneyPuck</TableHead>
              </TableRow>
              <TableRow className="hover:bg-transparent">
                {["Shots", "AUC", "Log loss", "xG / goals", "AUC", "Log loss", "xG / goals"].map((h, i) => <TableHead key={i} className={`${head} ${i ? "text-right" : ""}`}>{h}</TableHead>)}
              </TableRow>
            </TableHeader>
            <TableBody>
              {MP_ROWS.map(r => (
                <TableRow key={r[0]}>{r.map((v, i) => <TableCell key={i} className={`px-3 py-2 ${i ? "text-right" : ""}`}>{v}</TableCell>)}</TableRow>
              ))}
            </TableBody>
          </Table>
          <div className="mt-4" />
          <P><b>MoneyPuck is slightly ahead.</b> It ranks shots a little better and its totals sit closer to the goals scored; ours run about 4% under at 5 on 5 so far this season. The gap is small next to the noise in a third of a season.</P>
          <P><b>Why only this season.</b> MoneyPuck rescores past seasons with its current model, which was trained on 2023-24 to 2025-26, so its numbers for those seasons partly grade its own homework. On power-play shots from 2025-26 its AUC is 0.87; on this season&apos;s, which it hasn&apos;t trained on, it is 0.71. A comparison on past seasons flatters it.</P>
          <H3>Are the probabilities right?</H3>
          <P>Every unblocked shot of {seasonLabel(s)} so far, grouped by its xG. If the model is calibrated, shots it calls 10% go in about 10% of the time and the dots sit on the dashed line. The bars are 95% ranges, which get wide where there are few shots.</P>
          <CalibrationChart bins={m.bins} />
          <details className="mt-3 text-[13px]">
            <summary className="cursor-pointer text-muted-foreground hover:text-foreground">The numbers behind the chart</summary>
            <Table className="tabular mt-2 max-w-xl text-[13px]">
              <TableHeader className="bg-transparent">
                <TableRow className="hover:bg-transparent">
                  {["xG bin", "Shots", "Predicted", "Actual", "Goals"].map((h, i) => <TableHead key={h} className={`${head} ${i ? "text-right" : ""}`}>{h}</TableHead>)}
                </TableRow>
              </TableHeader>
              <TableBody>
                {m.bins.map(b => (
                  <TableRow key={b.lo}>
                    <TableCell className="px-3 py-1.5">{Math.round(b.lo * 100)}&ndash;{Math.round(b.hi * 100)}%</TableCell>
                    <TableCell className="px-3 py-1.5 text-right">{b.n.toLocaleString("en-US")}</TableCell>
                    <TableCell className="px-3 py-1.5 text-right">{(b.xg / b.n * 100).toFixed(1)}%</TableCell>
                    <TableCell className="px-3 py-1.5 text-right">{(b.rate * 100).toFixed(1)}%</TableCell>
                    <TableCell className="px-3 py-1.5 text-right">{b.goals}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </details>
          <H3>Does xG predict anything?</H3>
          <P>The test that matters for a team: take each number over its first games and see how well it predicts the team&apos;s <b>points % over the rest of the season</b>. Every regular season from {seasonLabel(validation.seasons[0])} to {seasonLabel(validation.seasons[validation.seasons.length - 1])}, every team, with at least {validation.min_rest} games still to play; the line is the correlation across teams, averaged over the seasons (1.0 would be a perfect forecast).</P>
          <ValidationChart data={validation} />
          <P><b>Early on, trust xG over the standings.</b> After 10 games a team&apos;s 5v5 xG share predicts its rest of the season better than its points % does, and it stays ahead for roughly the first {validationCross} games, the stretch where a record is mostly bounces and hot goaltending. Later the standings catch up and edge ahead: by then a record also carries real finishing and goaltending, which xG leaves out on purpose. Deserved points % (each game&apos;s expected points from its deserve-to-win) tracks xG share, since it comes from the same shots.</P>
          <P>The served model was trained on {seasonLabel(validation.seasons[0])} to 2024-25 and calibrated on 2025-26, so these seasons aren&apos;t out of sample for it. It never sees which team took a shot, so that shouldn&apos;t flatter xG much; switch to {seasonLabel(validation.last.season)} alone for the most recent season by itself, though one season of teams is a small, noisy sample.</P>
          <H3>Why xG differs from site to site</H3>
          <P>Every public xG model is built on the same NHL play-by-play, but no two are built the same way, so the same team or goalie gets different numbers on different sites. Against MoneyPuck this season, team xG totals are 3% apart on average and up to 8% for single teams, while each team&apos;s share of the xG in its games rarely moves by more than a point. Over a full season the goalie numbers spread further: on 2025-26 shots, goals saved above expected from the two models differed by 5 goals for a typical starter and by up to 15.</P>
          <P><b>Which shots count.</b> Most models, ours included, score only unblocked shots, and blocked ones carry no xG. NHL EDGE doesn&apos;t publish xG at all; its goalie stat, Saves Above Projected, uses its own shot model and leaves out attempts from beyond 60 feet, from behind the goal line and on an empty net (<a className="underline" href="https://www.nhl.com/news/nhl-edge-stats-jesper-wallstedt-minnesota-wild-2026-27">NHL.com</a>), so it can&apos;t match anyone&apos;s goals saved above expected.</P>
          <P><b>Adjusted versions.</b> MoneyPuck also publishes flurry-adjusted xG, which gives less credit to the second and third shots of a scramble, and score-adjusted xG, which gives more credit to teams that are leading or on the road (<a className="underline" href="https://moneypuck.com/glossary.htm">glossary</a>). An article quoting one of those versions won&apos;t match raw xG from anywhere. Our numbers are raw.</P>
          <P><b>Rebounds and rushes.</b> This is where the models disagree most. MoneyPuck rates rebounds and quick-transition shots much higher than we do, and rates shots from 20 to 45 feet lower. Teams that live on second chances look better there; teams that shoot from the slot look better here.</P>
          <P><b>Rinks.</b> Each arena&apos;s scorer places shots a little differently. MoneyPuck corrects each rink&apos;s coordinates (<a className="underline" href="https://moneypuck.com/data.htm">data notes</a>); we don&apos;t yet. In a few rinks our totals run well above MoneyPuck&apos;s, the pattern a scorer&apos;s bias would leave.</P>
          <P><b>Strength and training.</b> Evolving-Hockey fits separate models for even strength, the power play, the penalty kill and empty nets (<a className="underline" href="https://evolving-hockey.com/blog/a-new-expected-goals-model-for-predicting-goals-in-the-nhl/">method</a>); MoneyPuck and we fit one model with the strength as an input. Each site trains on different seasons and refits on its own schedule, and logging drifts from year to year, so the same shot can be worth a little more on one site than another.</P>
          <H3>Caveats</H3>
          <P><b>The league&apos;s logging drifts.</b> A shot within three seconds of another was 4% of non-goals in 2015 and 10% in 2025. The model weights recent seasons more and is recalibrated on the latest complete season, but it still slips a few percent a year, so it gets refit each summer.</P>
          <P><b>2025-26 game pages are partly in-sample.</b> The served model was calibrated on that season, so the site&apos;s 2025-26 xG totals match goals by construction. The 1.062 in the table is the evaluation model, which never saw 2025-26. This season&apos;s games are fully out of sample.</P>
          <P><b>Blocked shots</b> count as attempts but carry no xG; their coordinates are where they were blocked, not where they were taken.</P>
        </CardContent>
      </Card>
    </>
  );
}

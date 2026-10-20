import type { Metadata } from "next";
import { currentSeason, seasonIndex } from "@/lib/data";
import { seasonLabel } from "@/lib/format";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHead } from "@/components/site/page-head";
import { Tile } from "@/components/site/section";

export const metadata: Metadata = { title: "How the xG model works" };

const H3 = ({ children }: { children: React.ReactNode }) => <h2 className="mb-2 mt-7 text-base font-semibold tracking-[-0.015em]">{children}</h2>;
const P = ({ children }: { children: React.ReactNode }) => <p className="mb-3 max-w-[72ch] text-[15px] leading-relaxed text-secondary-foreground [&_b]:font-semibold [&_b]:text-foreground">{children}</p>;

const ROWS = [
  ["2024-25 (ours)", "0.767", "0.2206", "1.005"],
  ["2025-26 (ours)", "0.757", "0.2264", "1.062"],
  ["2025-26 (MoneyPuck)", "0.777", "0.2226", "1.004"],
  ["2026-27 so far (served model)", "0.776", "0.2246", "1.002"],
];

export default function Model() {
  const s = currentSeason();
  const g = seasonIndex(s).games;
  const xg = g.reduce((a, x) => a + x.hxg + x.axg, 0);
  // A shootout win adds a goal nobody shot.
  const goals = g.reduce((a, x) => a + x.hs + x.as - (x.end === "SO" ? 1 : 0), 0);
  const head = "h-9 px-3 text-xs font-medium normal-case tracking-normal";
  return (
    <>
      <PageHead title="How the xG model works" sub="Every unblocked shot priced as a goal probability." />
      <div className="mb-6 grid max-w-3xl grid-cols-1 gap-2 sm:grid-cols-3">
        <Tile label="Trained on">1.13M shots</Tile>
        <Tile label="Seasons">2015&ndash;2025</Tile>
        <Tile label={`${seasonLabel(s)} xG vs goals`}>{xg.toFixed(0)} / {goals}</Tile>
      </div>
      <Card className="max-w-4xl">
        <CardContent className="p-6">
          <P>Each unblocked shot gets a probability of becoming a goal, from a gradient-boosted model trained on every NHL shot since 2015-16 and built from the league&apos;s own play-by-play and shift charts, the same feed it scores after each game. A team&apos;s or player&apos;s xG is the sum of those probabilities.</P>
          <H3>What it looks at</H3>
          <P><b>The shot:</b> distance, angle, whether it came from behind the net, shot type, the shooter&apos;s handedness and wing. <b>The play before it:</b> what the previous event was, where, and how long ago; whether it&apos;s a rebound and off what (a save, a miss or a block); how fast the puck moved. <b>Game state:</b> strength (5v5, power play, pulled goalie and why), score, period, time. <b>Fatigue:</b> how long the shooter and both units had been on the ice.</P>
          <H3>What it can&apos;t see</H3>
          <P>The public feed doesn&apos;t log passes or zone entries, so <b>cross-ice feeds and true rushes are invisible</b>. The model uses proxies: seconds since the puck was last outside the zone, since the team won it, and whether the puck crossed the middle. They help a little. Screens, traffic, shot speed and where the shot was aimed aren&apos;t in the data at all.</P>
          <H3>How good it is</H3>
          <Table className="tabular text-[13px]">
            <TableHeader className="bg-transparent">
              <TableRow className="hover:bg-transparent">
                <TableHead className={head}>Held-out season</TableHead>
                <TableHead className={`${head} text-right`}>AUC</TableHead>
                <TableHead className={`${head} text-right`}>Log loss</TableHead>
                <TableHead className={`${head} text-right`}>xG / goals</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {ROWS.map(([l, auc, ll, r]) => (
                <TableRow key={l} className={l.includes("MoneyPuck") ? "text-muted-foreground" : ""}>
                  <TableCell className="px-3 py-2">{l}</TableCell>
                  <TableCell className="px-3 py-2 text-right">{auc}</TableCell>
                  <TableCell className="px-3 py-2 text-right">{ll}</TableCell>
                  <TableCell className="px-3 py-2 text-right">{r}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <div className="mt-4" />
          <P><b>AUC</b> is how well it ranks dangerous shots over safe ones (0.5 is a coin flip). <b>xG / goals</b> is whether the totals are right: 1.00 is perfect. The held-out rows were trained only through 2022-23 and never saw those seasons. MoneyPuck, the best-known public model, still ranks individual shots a little better; our inputs match theirs almost exactly, so the gap is in the modelling.</P>
          <H3>Caveats</H3>
          <P><b>The league&apos;s logging drifts.</b> A shot within three seconds of another was 4% of non-goals in 2015 and 10% in 2025. The model weights recent seasons more and is recalibrated on the latest complete season, but it still slips a few percent a year, so it gets refit each summer.</P>
          <P><b>2025-26 numbers here are partly in-sample:</b> the served model was calibrated on that season, so its xG totals match goals by construction. This season&apos;s games are fully out of sample.</P>
          <P><b>Blocked shots</b> count as attempts but carry no xG; their coordinates are where they were blocked, not where they were taken.</P>
        </CardContent>
      </Card>
    </>
  );
}

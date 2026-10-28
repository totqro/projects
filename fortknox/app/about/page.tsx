import type { Metadata } from "next";
import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { PageHead } from "@/components/site/page-head";

export const metadata: Metadata = {
  title: "About",
  description: "What High Slot is, where its numbers come from, and what every stat on the site means.",
};

const H2 = ({ children, id }: { children: React.ReactNode; id?: string }) => <h2 id={id} className="mb-2 mt-7 scroll-mt-6 text-base font-semibold tracking-[-0.015em] first:mt-0">{children}</h2>;
const P = ({ children }: { children: React.ReactNode }) => <p className="mb-3 max-w-[72ch] text-[15px] leading-relaxed text-secondary-foreground [&_a]:text-foreground [&_a]:underline [&_a]:underline-offset-4 [&_b]:font-semibold [&_b]:text-foreground">{children}</p>;

/** The terms a newcomer meets first, in the order they meet them. */
const GLOSSARY: [string, React.ReactNode][] = [
  ["xG (expected goals)", "The chance an unblocked shot becomes a goal, from where and how it was taken and what happened just before. A 0.25 xG shot goes in about one time in four. Add up a team's shots and you get how many goals its chances were worth."],
  ["Deserve to win", "Each team's chance of winning had the game's shots been taken again, every one going in with its xG as the chance (empty-net shots left out; a game level on goals counts as a coin flip, like a shootout). It weighs the shots one by one, so ten 0.1 xG chances and one 1.0 chance are not the same game. \"Won at 31%\" on a box score marks a win the shots gave the winner only a 31% chance of."],
  ["xG share (xG%)", "xG for divided by xG for plus against. Above 50% means out-chancing the opponent. For a player it counts every shot while he was on the ice, his teammates' included; it measures the minutes he played, not his shots alone."],
  ["5v5", "Five skaters a side with both goalies in net. Most of a game, and the fairest place to compare teams and players, because power plays and penalty kills are stripped out."],
  ["ixG", "Individual expected goals: only the player's own shots."],
  ["GAx", "Goals above expected: goals minus xG. Positive means finishing better than an average shooter on the same chances. It swings a lot over a few weeks."],
  ["GSAx", "Goals saved above expected: the xG a goalie faced minus the goals he allowed. Positive means he stopped more than an average goalie would have."],
  ["Per 60 (/60)", "A total per 60 minutes of ice time, so a fourth-liner and a first-liner can be compared on the same footing."],
  ["On-ice / off-ice, Rel", "How his team did at 5v5 with him on the ice and with him on the bench, in the games he played. Rel is the difference: a positive Rel xG% means the team out-chanced opponents more with him than without him."],
  ["Lines and WOWY", "Forward trios and defence pairs at 5v5, and “with or without you”: how two teammates did together and apart. The best way to see whether a player drives results or rides along."],
];

export default function About() {
  return (
    <>
      <PageHead title="About High Slot" sub="Every NHL game, scored shot by shot." />
      <Card className="max-w-4xl">
        <CardContent>
          <H2>What this is</H2>
          <P>High Slot puts an expected-goals number on every shot of every NHL game, then adds them up into game sheets, standings, team and player tables, lines and goalie numbers. The question it answers is <b>who created the better chances</b>, which says more about how a team is playing than the score does over a handful of games.</P>
          <P>It&apos;s an independent project, free, with no ads and no account. Pages update through the day as games finish.</P>

          <H2>Where the numbers come from</H2>
          <P>Everything is built from the NHL&apos;s public play-by-play and shift charts. The model is a gradient-boosted classifier trained on 1.13 million shots since 2015-16; <Link href="/model">the model page</Link> covers what it looks at, what it can&apos;t see, how accurate it is, and how it compares with MoneyPuck&apos;s public model.</P>

          <H2>Reading the numbers</H2>
          <P><b>Early in a season, everything is noisy.</b> There just aren&apos;t many shots yet, so shooting and save percentages swing a lot from week to week. xG settles down sooner, which makes it the better early guide, but treat small samples as a hint, not a verdict. Tables let you set a minimum number of games or minutes.</P>

          <H2 id="glossary">Glossary</H2>
          <dl className="mb-4 max-w-[72ch] space-y-3 text-[15px] leading-relaxed">
            {GLOSSARY.map(([t, d]) => (
              <div key={t}>
                <dt className="font-semibold text-foreground">{t}</dt>
                <dd className="text-secondary-foreground">{d}</dd>
              </div>
            ))}
          </dl>
          <P>Every column heading on the site explains itself on hover.</P>

          <H2>Not affiliated with the NHL</H2>
          <P>High Slot isn&apos;t affiliated with or endorsed by the National Hockey League. NHL, team names and logos are trademarks of the NHL and its teams.</P>
        </CardContent>
      </Card>
    </>
  );
}

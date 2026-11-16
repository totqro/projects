import type { Metadata } from "next";
import Link from "next/link";
import { currentArticles, FORMATS, type Article } from "@/lib/articles";
import { fmtDate } from "@/lib/format";
import { PageHead } from "@/components/site/page-head";
import { HEADING } from "@/components/site/section";
import { TeamLogo } from "@/components/site/team-logo";

export const metadata: Metadata = {
  title: "Articles",
  description: "The week in expected goals, regression watch, and a report on every NHL team, rewritten after every game.",
};

const Item = ({ a }: { a: Article }) => (
  <li className="py-4 first:pt-0">
    <Link href={`/articles/${a.slug}`} className="group block">
      <div className="mb-1 text-xs font-medium uppercase tracking-[0.06em] text-muted-foreground">{FORMATS[a.format].name} · Through {fmtDate(a.through)}</div>
      <h2 className="text-lg font-semibold leading-snug tracking-[-0.015em] group-hover:underline group-hover:underline-offset-4">{a.title}</h2>
      <p className="mt-1 text-[15px] text-secondary-foreground">{a.dek}</p>
    </Link>
  </li>
);

export default function Articles() {
  const all = currentArticles();
  const league = all.filter(a => a.format !== "team"), teams = all.filter(a => a.format === "team");
  if (!all.length) return <><PageHead title="Articles" /><p className="text-muted-foreground">No games yet this season.</p></>;
  return (
    <>
      <PageHead title="Articles" sub="Written from the numbers, rewritten after every game." />
      <ul className="max-w-3xl divide-y divide-border">{league.map(a => <Item key={a.slug} a={a} />)}</ul>
      <h2 className={`${HEADING} mb-1 mt-10`}>{FORMATS.team.name}s</h2>
      <p className="mb-4 max-w-3xl text-[15px] text-muted-foreground">{FORMATS.team.about}</p>
      <ul className="grid max-w-5xl gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
        {teams.map(a => (
          <li key={a.slug}>
            <Link href={`/articles/${a.slug}`} className="group flex items-start gap-2.5">
              <TeamLogo team={a.team!} size={22} className="mt-0.5" />
              <span className="text-[15px] leading-snug group-hover:underline group-hover:underline-offset-4">{a.title}</span>
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}

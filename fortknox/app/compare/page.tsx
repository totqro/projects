import type { Metadata } from "next";
import { Suspense } from "react";
import { currentSeason } from "@/lib/data";
import { PageHead } from "@/components/site/page-head";
import { CompareView } from "@/components/players/compare-view";

export const metadata: Metadata = {
  title: "Compare players",
  description: "NHL skaters or goalies side by side: expected goals, on-ice numbers and where each ranks in the league.",
};

export default function Compare() {
  return (
    <>
      <PageHead title="Compare players" sub="Up to four skaters or goalies side by side, each number with where it ranks in the league." />
      <Suspense>
        <CompareView current={currentSeason()} />
      </Suspense>
    </>
  );
}

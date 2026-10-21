"use client";

import * as React from "react";
import { pickSeason, usePickedSeason } from "@/components/site/nav";
import { Segmented } from "@/components/teams/teams-view";

/** A player's page, one season at a time. Follows the nav's season picker,
 *  falling back to his latest season when he didn't play in the one picked. */
export function PlayerSeasons({ blocks }: { blocks: { season: number; label: string; node: React.ReactNode }[] }) {
  const picked = usePickedSeason();
  const shown = blocks.find(b => b.season === picked) ?? blocks[0];
  if (!shown) return null;
  return (
    <>
      {blocks.length > 1 && (
        <div className="mb-5">
          <Segmented label="Season" value={String(shown.season)} onChange={v => pickSeason(+v)}
            options={blocks.map(b => [String(b.season), b.label] as [string, string])} />
        </div>
      )}
      {shown.node}
    </>
  );
}

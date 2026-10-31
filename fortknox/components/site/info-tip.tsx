"use client";

import * as React from "react";
import { Info } from "lucide-react";
import { TIPS } from "@/lib/teams";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

/** An (i) icon that explains a stat: opens on hover, and on tap for touch screens. */
export function InfoTip({ tip, label }: { tip: string; label?: string }) {
  const [open, setOpen] = React.useState(false);
  const text = TIPS[tip] ?? tip;
  return (
    <Tooltip open={open} onOpenChange={setOpen}>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label={label ? `About ${label}` : "More info"}
          onClick={() => setOpen(o => !o)}
          className="ml-1 inline-flex size-4 translate-y-[-1px] items-center justify-center rounded-full align-middle text-muted-foreground/80 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Info className="size-3.5" strokeWidth={2.25} />
        </button>
      </TooltipTrigger>
      <TooltipContent className="max-w-72 text-pretty normal-case leading-relaxed tracking-normal">{text}</TooltipContent>
    </Tooltip>
  );
}

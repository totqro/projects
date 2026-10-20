import Image from "next/image";
import { cn } from "@/lib/utils";

/** A team's logo, the dark-background version the NHL serves for its own site. */
export function TeamLogo({ team, size = 20, className }: { team: string; size?: number; className?: string }) {
  return (
    <Image src={`https://assets.nhle.com/logos/nhl/svg/${team}_dark.svg`} alt="" width={size} height={size}
      className={cn("inline-block shrink-0 object-contain", className)} style={{ width: size, height: size }} />
  );
}

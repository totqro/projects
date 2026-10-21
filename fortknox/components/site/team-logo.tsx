import Image from "next/image";
import { cn } from "@/lib/utils";

/** A team's logo, the dark-background version the NHL draws for its own
 *  site, served from public/logos/ so a change on the NHL's side can't
 *  blank every logo here. */
export function TeamLogo({ team, size = 20, className }: { team: string; size?: number; className?: string }) {
  return (
    <Image src={`/logos/${team}.svg`} alt="" width={size} height={size}
      className={cn("inline-block shrink-0 object-contain", className)} style={{ width: size, height: size }} />
  );
}

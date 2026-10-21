import Link from "next/link";
import { PageHead } from "@/components/site/page-head";

export default function NotFound() {
  return (
    <>
      <PageHead title="Nothing in the slot" sub="That page doesn't exist, or the game hasn't been played yet." />
      <p className="flex flex-wrap gap-x-5 gap-y-2 text-[15px]">
        <Link href="/" className="underline underline-offset-4">Tonight&apos;s games</Link>
        <Link href="/about" className="underline underline-offset-4">About High Slot</Link>
      </p>
    </>
  );
}

import type { NextConfig } from "next";

// A fully static site: every game, team and player page is pre-rendered at
// build time from the published sheets in data/ (see scripts/fetch-data.sh).
const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },
  devIndicators: false,
  // A fixed id keeps unchanged pages byte-identical from one build to the
  // next, so a deploy only uploads the games and pages that actually changed
  // (asset filenames are content-hashed already).
  generateBuildId: async () => "fortknox",
};

export default nextConfig;

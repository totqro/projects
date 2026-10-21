import { dirname } from "path";
import { fileURLToPath } from "url";
import { FlatCompat } from "@eslint/eslintrc";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({
  baseDirectory: __dirname,
});

const eslintConfig = [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    ignores: [
      "node_modules/**",
      ".next/**",
      "out/**",
      "build/**",
      "next-env.d.ts",
      // The Inset Dark registry (npx shadcn add ... inset-dark/all.json) and
      // its rules file: vendored, kept as installed.
      "components/ui/**",
      ".better-design/**",
      "data/**",
      // The Python scoring pipeline, with its venv and raw-feed cache.
      "pipeline/**",
    ],
  },
];

export default eslintConfig;

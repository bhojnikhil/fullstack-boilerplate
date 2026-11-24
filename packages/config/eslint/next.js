// Shared ESLint flat config for Next.js apps.
//
// eslint-config-next 15 ships legacy (eslintrc) configs, so they are loaded
// through FlatCompat. Resolution happens from this package, which owns the
// eslint-config-next dependency.
import { FlatCompat } from "@eslint/eslintrc";
import path from "node:path";
import { fileURLToPath } from "node:url";

const compat = new FlatCompat({
  baseDirectory: path.dirname(fileURLToPath(import.meta.url)),
});

/** @type {import("eslint").Linter.Config[]} */
const config = [
  {
    ignores: [".next/**", "out/**", "node_modules/**", "next-env.d.ts"],
  },
  ...compat.extends("next/core-web-vitals", "next/typescript"),
];

export default config;

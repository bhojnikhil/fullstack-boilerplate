// Shared ESLint flat config for Next.js apps.
//
// eslint-config-next 15 ships legacy (eslintrc) configs, so they are loaded
// through FlatCompat. Resolution happens from this package, which owns the
// eslint-config-next dependency. Plugins resolve from eslint-config-next's own
// dependencies: resolving them from here would pick whatever version pnpm
// happens to hoist (e.g. eslint-config-expo's newer eslint-plugin-react-hooks).
import { FlatCompat } from "@eslint/eslintrc";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);

const compat = new FlatCompat({
  baseDirectory: path.dirname(fileURLToPath(import.meta.url)),
  resolvePluginsRelativeTo: path.dirname(
    require.resolve("eslint-config-next/package.json"),
  ),
});

/** @type {import("eslint").Linter.Config[]} */
const config = [
  {
    ignores: [".next/**", "out/**", "node_modules/**", "next-env.d.ts"],
  },
  ...compat.extends("next/core-web-vitals", "next/typescript"),
];

export default config;

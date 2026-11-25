# 0006. Mobile toolchain versions: TypeScript 6, ESLint 9, pinned eas-cli

- Status: Accepted
- Date: 2026-11-24

## Context

The repo pins exact versions and prefers current stable releases. On 2026-11-24 the
latest releases were TypeScript 7.0.2, ESLint 10.15.0 and eas-cli 27.11.0, while
`apps/mobile` is on Expo SDK 58.

## Decision

- **TypeScript 6.0.3, not 7.** Expo's versions API (`api.expo.dev/v2/versions`) lists
  `typescript: ~6.0.3` as the related package for SDK 58, and `npx expo install`
  resolves `typescript@~6.0.3`. Expo's tooling (`expo/tsconfig.base`, `expo-doctor`,
  typed routes) is tested against that line. The web app also uses 6.0.3.
- **ESLint 9.39.5, not 10.** `eslint-config-expo` 58.0.4 (the SDK 58 line) depends on
  `eslint-plugin-import` 2.32.0 (peer `eslint` up to `^9`) and `eslint-plugin-react`
  7.37.5 (peer up to `^9.7`). Neither declares ESLint 10 support. The shared
  `@repo/config` (peer `eslint ^9`) and `eslint-config-next` 15 for the web app are in
  the same position, so the workspace stays on one ESLint major.
- **eas-cli 27.11.0 as an exact devDependency of the workspace root**, run with
  `pnpm exec eas` from `apps/mobile` (pnpm resolves the root's binaries), and `eas.json`
  `cli.version` set to the same version. Not a dependency of `apps/mobile` itself:
  expo-doctor fails the app if eas-cli is in its package.json ("Check for legacy global
  CLI installed locally"). Docs don't use `npx eas-cli@latest`. Its install scripts that pnpm would run are denied in
  `pnpm-workspace.yaml` (`dtrace-provider`, an optional native addon of its logger, and
  `protobufjs`'s version notice).

## Consequences

- Revisit when an Expo SDK lists TypeScript 7 and when `eslint-config-expo`'s plugins
  support ESLint 10 (check with `npm view <plugin> peerDependencies`).
- Upgrading eas-cli is a deliberate change: bump the root devDependency, the lockfile
  and `eas.json` `cli.version` together.

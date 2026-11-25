# 0002. JS monorepo: pnpm workspaces + Turborepo

- Status: Accepted
- Date: 2026-11-24

## Context

The frontend was a standalone npm project (`client/`). The v2 plan adds a mobile app
(`apps/mobile`) and shared packages (`packages/config`, later a generated
`packages/api-client`) that several apps consume.

## Decision

- **pnpm workspaces** (`pnpm-workspace.yaml`: `apps/*`, `packages/*`), with the pnpm
  version pinned in the root `package.json` `packageManager` field and one root
  `pnpm-lock.yaml`. Workspace packages depend on each other with `workspace:*`.
- **Turborepo** runs `lint`, `typecheck`, `build` and `dev` across packages, with
  `dependsOn: ["^task"]` so shared packages are handled before their consumers. Remote
  caching is not configured.
- **`packages/config`** (`@repo/config`) holds the shared TypeScript base configs,
  ESLint flat config and Prettier config. The Next.js config uses native flat
  exports as of Next.js 16. See [ADR 0005](0005-web-foundation.md) for compatible
  ESLint and TypeScript versions.
- The Python API stays outside the JS workspace. The root `Makefile` is the single entry
  point that drives both uv and pnpm/Turborepo.
- Workspace package names are fixed (`web`, `@repo/config`), not template placeholders.

## Consequences

- One install and one lockfile for all JS apps; shared configuration without copy-paste.
- Docker builds for JS apps use the repository root as build context (for the lockfile),
  filtered by a per-Dockerfile ignore file (`apps/web/Dockerfile.dockerignore`).
- Node 25+ no longer bundles Corepack, so pnpm is installed explicitly (pinned) in the
  Dockerfile and by `pnpm/action-setup` in CI.

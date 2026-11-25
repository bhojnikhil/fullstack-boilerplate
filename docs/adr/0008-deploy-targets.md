# ADR 0008: Deploy targets and release workflows

Status: Accepted

The API and the future worker share an image and a database, so they run as process
groups of one Fly.io app. Fly's `release_command` runs Alembic before traffic moves and
aborts the deploy on failure, which gives migrations an owner-role connection without a
separate pipeline stage. Postgres is Neon: a pooled URL for the application role and a
direct URL for the owner role used by migrations, so a later non-owner application role
(for Row-Level Security) needs no code change. Cloud Run is documented, not automated.

Web deploys to Vercel from the workflow with a pinned CLI. Cloudflare Pages is not
wired because Next.js there needs an adapter this repository has not been run with.

Deploy workflows read their credentials from GitHub Environments (`staging`,
`production`) and check for them in a first step, so they skip with a notice instead of
failing when secrets are absent. Staging deploys after CI succeeds on `main`;
production is manual. The mobile release workflow is manual, uses the repository's
pinned `eas-cli`, and publishes OTA updates only through `pnpm release:update`.

CI is path-filtered inside `ci.yml` with plain `git diff` (no third-party filter action),
and a final `CI gate` job aggregates the results, so one required check works whichever
jobs the change triggers. Mobile CI became a reusable workflow so the gate can see it.

None of this has run against real accounts. It is validated with `actionlint`, a local
test of the path filter and a TOML parse of `fly.toml`.

# syntax=docker/dockerfile:1
#
# Build context: the repository root (pnpm workspace + lockfile live there).
#   docker build -f apps/web/Dockerfile --build-arg NEXT_PUBLIC_API_URL=... .
# The context is filtered by apps/web/Dockerfile.dockerignore.

ARG NODE_IMAGE=node:26.13.1-alpine

FROM ${NODE_IMAGE} AS base
ENV NEXT_TELEMETRY_DISABLED=1

# ---------------------------------------------------------------------------
FROM base AS deps
# Node 25+ no longer bundles Corepack; install the pinned pnpm directly.
RUN npm install -g pnpm@12.23.0
WORKDIR /repo
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/
COPY packages/config/package.json packages/config/
COPY packages/api-client/package.json packages/api-client/
RUN --mount=type=cache,id=pnpm-store,target=/pnpm-store \
    pnpm install --frozen-lockfile --store-dir /pnpm-store --filter web...

# ---------------------------------------------------------------------------
FROM deps AS builder
COPY packages/config packages/config
COPY packages/api-client packages/api-client
COPY apps/web apps/web
# NEXT_PUBLIC_* values are inlined into the bundle by `next build`, so the
# public API URL must be provided at build time. It must be reachable from the
# user's browser.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_GOOGLE_CLIENT_ID=
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL} NEXT_PUBLIC_GOOGLE_CLIENT_ID=${NEXT_PUBLIC_GOOGLE_CLIENT_ID}
RUN pnpm --filter web build \
    # Readable by the runtime user regardless of the host checkout's file modes
    # (e.g. 600 under a restrictive umask); writable by root only.
    && chmod -R u=rwX,go=rX apps/web/.next/standalone apps/web/.next/static apps/web/public

# ---------------------------------------------------------------------------
# Runtime: Next.js standalone server only (no pnpm, no dev dependencies).
FROM base AS runtime
ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3000
WORKDIR /app
# Root-owned and read-only for the runtime user (permissions set in builder).
COPY --from=builder /repo/apps/web/.next/standalone ./
COPY --from=builder /repo/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder /repo/apps/web/public ./apps/web/public
# Built-in unprivileged user of the official Node images.
USER node
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:3000/',{redirect:'manual'}).then(r=>process.exit(r.ok?0:1),()=>process.exit(1))"]
CMD ["node", "apps/web/server.js"]

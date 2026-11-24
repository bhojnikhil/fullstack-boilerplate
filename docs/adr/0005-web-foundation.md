# 0005. Web foundation and mobile association documents

- Status: Accepted
- Date: 2026-11-24

## Context

The web app used Next.js 15 with legacy ESLint configs loaded through FlatCompat.
The public site needs theme-aware components, accessible forms, and the association
documents used to open supported links in mobile apps.

## Decision

- Use Next.js 16 and its native flat ESLint exports. Use TypeScript 6.0.3 and
  ESLint 9.39.5. Next's typescript-eslint dependencies require TypeScript below 6.1,
  and its React, import and accessibility plugins declare support through ESLint 9.
- Use Tailwind CSS 4 with CSS variables for the palettes. Keep the button, input,
  and label sources installed by `pnpm --dir apps/web dlx shadcn@4.23.0 add button input label`.
  Import the individual Radix primitives used by those components. The shadcn
  registry uses the pre-1.0 `cn` package for merging Tailwind classes. Keep it
  pinned and re-export it through `@/lib/utils` so that registry items using the
  configured alias resolve to the same helper.
- Use next-themes for system detection and persistence. Its server-rendered inline
  script applies the theme before hydration. Give the script an inert type for
  client-only renders through `scriptProps` because React 19 warns about executing
  scripts created by client-rendered components. A future CSP that restricts
  scripts will need to pass a per-request nonce to the theme provider and include
  it in the policy. Deny embedding with `frame-ancestors 'none'` and
  `X-Frame-Options: DENY`, send `nosniff` and `strict-origin-when-cross-origin`, and
  disable the `X-Powered-By` header.
- Serve association JSON from explicit App Router handlers using runtime environment
  variables. The same standalone image can serve different mobile app IDs. Return
  404 for missing or malformed settings and cache successful responses for an hour.
  Default to `/app/*` for iOS and allow the operator to set paths with
  `IOS_APPLINK_PATHS` as the mobile routes are defined.
- Require npm releases to be at least seven days old through pnpm's
  `minimumReleaseAge` setting. Keep direct dependencies and the resolved workspace
  lockfile pinned so the maturity policy is checked during frozen installs.
- Use Vitest for render and handler contracts. Run Playwright Chromium against
  the standalone production build and check the association URLs and runtime
  public page values in the existing container job.

## Consequences

The public deletion page can take requests through an operator's mailbox once that
mailbox is configured. App registrations, signing certificates, and platform link
verification belong to the consuming project.

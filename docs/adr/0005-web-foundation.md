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
  Import the individual Radix primitives used by those components. Use next-themes
  for system detection and persistence of the theme choice.
- Serve association JSON from explicit App Router handlers using runtime environment
  variables. The same standalone image can serve different mobile app IDs. Return
  404 for missing or malformed settings. Start with `/app/*` for iOS so public
  policy and support URLs remain on the web. Align the scope with the mobile routes
  when those are defined.
- Use Vitest for render and handler contracts, Playwright Chromium for browser and
  HTTP smoke coverage, and the existing container job for standalone packaging.

## Consequences

The public deletion page can take requests through an operator's mailbox once that
mailbox is configured. App registrations, signing certificates, and platform link
verification belong to the consuming project.

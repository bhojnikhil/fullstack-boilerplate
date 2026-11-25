# 0005. Mobile styling: StyleSheet + typed design tokens

- Status: Accepted
- Date: 2026-11-24

## Context

`apps/mobile` (Expo SDK 58, React Native 0.88, New Architecture) needs a styling
approach with light/dark design tokens. The candidates considered, checked against the
npm registry on 2026-11-24:

- **NativeWind** (Tailwind class names on React Native). The stable line is 4.2.7, which
  builds on Tailwind CSS 3 and adds a Babel preset, a Metro transformer and
  `react-native-css-interop`. NativeWind 5, which targets Tailwind 4, is a release
  candidate (`5.0.0-rc.1`). The web app is expected to use Tailwind 4 (phase 8), so the
  stable NativeWind would not share its Tailwind version anyway.
- **Unistyles 3** (3.8.2). Fast, theme-aware `StyleSheet` replacement, but built on
  Nitro Modules (native code), so the app could no longer run in Expo Go, and it adds a
  Babel plugin.
- **React Native `StyleSheet` / inline styles + a typed token module**: what Expo's own
  SDK 58 template does. No extra dependencies or build steps.

## Decision

Use React Native's built-in styling with a small typed token module:

- `src/theme/tokens.ts` defines `colors.light` / `colors.dark` (same keys, enforced by a
  test), `spacing`, `radius`, `typography` and `MIN_TOUCH_TARGET`. Colors follow the
  neutral (zinc) scale and token names that shadcn/ui uses on the web (`background`,
  `surface`, `text`, `textMuted`, `border`, `primary`, `danger`, ...), so the two apps
  share a vocabulary even though they share no code.
- `useTheme()` returns the tokens for the OS color scheme (`userInterfaceStyle:
  "automatic"`); `toNavigationTheme()` maps them onto Expo Router's navigation theme.
- Tests check that light/dark define the same tokens and that the pairs the components
  draw together meet WCAG AA: 4.5:1 for text, and 3:1 for the outlines and fills that
  identify controls (`controlBorder` for inputs and secondary buttons; `border` is only
  for decorative dividers).

## Consequences

- No Babel/Metro customization and no native styling module: the app still runs in Expo
  Go, and Jest needs no extra setup for styles.
- Styles are plain objects next to components. There are no utility classes, so styles
  are more verbose than NativeWind, and responsive/variant helpers must be written by
  hand if needed.
- Tokens are duplicated between web and mobile rather than generated from one source. If
  that drift becomes a problem, extract them into a shared package (for example
  `packages/design-tokens`) that both apps import.
- Switching to NativeWind 5 or Unistyles later is contained: screens read tokens through
  `useTheme()`, so a migration replaces that hook and the component styles, not the
  token values.

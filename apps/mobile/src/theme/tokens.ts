/**
 * Design tokens (light + dark). Plain values consumed through `useTheme()` and
 * React Native StyleSheet; see docs/adr/0005-mobile-styling.md.
 *
 * The palette mirrors the neutral (zinc) scale that shadcn/ui uses on the web,
 * so both apps share the same vocabulary: background/surface/text/muted/
 * border/primary/danger. src/theme/__tests__/tokens-test.ts checks every pair
 * the components draw together against WCAG 2.2 AA: 4.5:1 for text (1.4.3)
 * and 3:1 for the outlines that identify controls (1.4.11).
 */

export type ColorSchemeName = "light" | "dark";

export interface ColorTokens {
  /** Screen background. */
  background: string;
  /** Cards, inputs, grouped rows. */
  surface: string;
  text: string;
  textMuted: string;
  /** Decorative separators (list dividers). No contrast requirement. */
  border: string;
  /** Outlines that identify a control (inputs, secondary buttons): >= 3:1. */
  controlBorder: string;
  primary: string;
  onPrimary: string;
  danger: string;
  onDanger: string;
  /** Offline / warning banner. */
  warningBackground: string;
  onWarning: string;
}

export const colors: Record<ColorSchemeName, ColorTokens> = {
  light: {
    background: "#ffffff",
    surface: "#f4f4f5",
    text: "#09090b",
    textMuted: "#52525b",
    border: "#d4d4d8",
    controlBorder: "#71717a",
    primary: "#18181b",
    onPrimary: "#fafafa",
    danger: "#b91c1c",
    onDanger: "#ffffff",
    warningBackground: "#fef3c7",
    onWarning: "#78350f",
  },
  dark: {
    background: "#09090b",
    surface: "#18181b",
    text: "#fafafa",
    textMuted: "#a1a1aa",
    border: "#3f3f46",
    controlBorder: "#71717a",
    primary: "#fafafa",
    onPrimary: "#18181b",
    danger: "#f87171",
    onDanger: "#450a0a",
    warningBackground: "#451a03",
    onWarning: "#fde68a",
  },
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
} as const;

export const radius = {
  sm: 6,
  md: 10,
  lg: 16,
} as const;

export const typography = {
  title: { fontSize: 28, lineHeight: 34, fontWeight: "700" },
  heading: { fontSize: 20, lineHeight: 26, fontWeight: "600" },
  body: { fontSize: 16, lineHeight: 24, fontWeight: "400" },
  label: { fontSize: 14, lineHeight: 20, fontWeight: "600" },
  caption: { fontSize: 13, lineHeight: 18, fontWeight: "400" },
} as const;

/** Minimum touch target (dp), per Android/iOS accessibility guidance. */
export const MIN_TOUCH_TARGET = 48;

export interface Theme {
  scheme: ColorSchemeName;
  colors: ColorTokens;
  spacing: typeof spacing;
  radius: typeof radius;
  typography: typeof typography;
}

const themes: Record<ColorSchemeName, Theme> = {
  light: { scheme: "light", colors: colors.light, spacing, radius, typography },
  dark: { scheme: "dark", colors: colors.dark, spacing, radius, typography },
};

/** Resolves the OS scheme (which may be null/"unspecified") to a theme. */
export function getTheme(scheme: string | null | undefined): Theme {
  return scheme === "dark" ? themes.dark : themes.light;
}

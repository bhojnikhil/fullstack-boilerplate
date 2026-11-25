import { DarkTheme, DefaultTheme, type Theme as NavigationTheme } from "expo-router";

import { getTheme, type Theme } from "./tokens";
import { useColorScheme } from "./use-color-scheme";

/** Current design tokens, following the OS light/dark setting. */
export function useTheme(): Theme {
  return getTheme(useColorScheme());
}

/** Maps design tokens onto the navigation theme (headers, tab bar, cards). */
export function toNavigationTheme(theme: Theme): NavigationTheme {
  const base = theme.scheme === "dark" ? DarkTheme : DefaultTheme;
  return {
    ...base,
    colors: {
      ...base.colors,
      primary: theme.colors.primary,
      background: theme.colors.background,
      card: theme.colors.background,
      text: theme.colors.text,
      border: theme.colors.border,
      notification: theme.colors.danger,
    },
  };
}

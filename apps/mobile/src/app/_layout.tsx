import { Stack, ThemeProvider } from "expo-router";
import { StatusBar } from "expo-status-bar";

import { NetworkStatusBoundary } from "@/components/network-banner";
import { AppProviders } from "@/providers/app-providers";
import { toNavigationTheme, useTheme } from "@/theme/use-theme";

export default function RootLayout() {
  const theme = useTheme();
  return (
    <AppProviders>
      <ThemeProvider value={toNavigationTheme(theme)}>
        {/* Edge-to-edge: the status bar is transparent; pick readable icons. */}
        <StatusBar style={theme.scheme === "dark" ? "light" : "dark"} />
        <NetworkStatusBoundary>
          <Stack screenOptions={{ headerShown: false }}>
            <Stack.Screen name="index" />
            <Stack.Screen name="(auth)" />
            <Stack.Screen name="(app)" />
          </Stack>
        </NetworkStatusBoundary>
      </ThemeProvider>
    </AppProviders>
  );
}

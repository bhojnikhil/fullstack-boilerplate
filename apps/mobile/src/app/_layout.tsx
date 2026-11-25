import { Stack, ThemeProvider } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { ActivityIndicator, View } from "react-native";

import { NetworkStatusBoundary } from "@/components/network-banner";
import { UpdateRequiredScreen } from "@/components/update-required";
import { AppLockGate } from "@/features/lock/app-lock";
import { SessionGate } from "@/providers/session-gate";
import { ServicesProvider, useSession, useUpdateRequired } from "@/providers/services";
import { toNavigationTheme, useTheme } from "@/theme/use-theme";

function RootStack() {
  const { status } = useSession();
  const updateRequired = useUpdateRequired();
  const { colors } = useTheme();
  if (updateRequired)
    return <UpdateRequiredScreen minVersion={updateRequired.minVersion} />;
  if (status === "loading") {
    return (
      <View
        style={{
          flex: 1,
          justifyContent: "center",
          backgroundColor: colors.background,
        }}
      >
        <ActivityIndicator accessibilityLabel="Loading" color={colors.text} />
      </View>
    );
  }
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="index" />
      <Stack.Protected guard={status === "signedOut"}>
        <Stack.Screen name="(auth)" />
      </Stack.Protected>
      <Stack.Protected guard={status === "signedIn"}>
        <Stack.Screen name="(app)" />
      </Stack.Protected>
      {/* Reachable signed in or out: email links and invitations. */}
      <Stack.Screen name="auth" />
      <Stack.Screen name="invite/[token]" />
    </Stack>
  );
}

export default function RootLayout() {
  const theme = useTheme();
  return (
    <ServicesProvider>
      <SessionGate>
        <ThemeProvider value={toNavigationTheme(theme)}>
          {/* Edge-to-edge: the status bar is transparent; pick readable icons. */}
          <StatusBar style={theme.scheme === "dark" ? "light" : "dark"} />
          <AppLockGate>
            <NetworkStatusBoundary>
              <RootStack />
            </NetworkStatusBoundary>
          </AppLockGate>
        </ThemeProvider>
      </SessionGate>
    </ServicesProvider>
  );
}

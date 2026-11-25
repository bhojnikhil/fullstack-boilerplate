import type { ReactNode } from "react";
import { Text, View } from "react-native";
import {
  SafeAreaInsetsContext,
  useSafeAreaInsets,
} from "react-native-safe-area-context";

import { useIsOffline } from "@/lib/network";
import { useTheme } from "@/theme/use-theme";

export const OFFLINE_MESSAGE = "You're offline. Some content may be out of date.";

/** Banner shown while the device has no usable connection. */
export function NetworkBanner({ topInset = 0 }: { topInset?: number }) {
  const offline = useIsOffline();
  const { colors, spacing, typography } = useTheme();
  if (!offline) return null;
  return (
    <View
      testID="network-banner"
      // One focusable element, announced when it appears (Android live region;
      // iOS VoiceOver reads alerts on focus).
      accessible
      accessibilityRole="alert"
      accessibilityLiveRegion="polite"
      style={{
        backgroundColor: colors.warningBackground,
        paddingTop: topInset + spacing.sm,
        paddingBottom: spacing.sm,
        paddingHorizontal: spacing.lg,
      }}
    >
      <Text
        style={[typography.caption, { color: colors.onWarning, textAlign: "center" }]}
      >
        {OFFLINE_MESSAGE}
      </Text>
    </View>
  );
}

/**
 * Renders the banner above the navigator. While it is visible the banner
 * consumes the top safe-area inset, and children (headers, screens) see a top
 * inset of 0 so the status-bar gap isn't applied twice.
 */
export function NetworkStatusBoundary({ children }: { children: ReactNode }) {
  const offline = useIsOffline();
  const insets = useSafeAreaInsets();
  return (
    <View style={{ flex: 1 }}>
      <NetworkBanner topInset={insets.top} />
      <SafeAreaInsetsContext.Provider value={offline ? { ...insets, top: 0 } : insets}>
        {children}
      </SafeAreaInsetsContext.Provider>
    </View>
  );
}

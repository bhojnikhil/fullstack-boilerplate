import { Link, Stack } from "expo-router";
import { Text } from "react-native";

import { Screen } from "@/components/screen";
import { useTheme } from "@/theme/use-theme";

export default function NotFound() {
  const { colors, spacing, typography } = useTheme();
  return (
    <>
      <Stack.Screen options={{ headerShown: true, title: "Not found" }} />
      <Screen
        edges={["bottom", "left", "right"]}
        style={{ padding: spacing.xl, gap: spacing.lg }}
      >
        <Text
          accessibilityRole="header"
          style={[typography.heading, { color: colors.text }]}
        >
          This screen doesn&apos;t exist.
        </Text>
        <Link href="/" style={[typography.body, { color: colors.text }]}>
          Go to the start screen
        </Link>
      </Screen>
    </>
  );
}

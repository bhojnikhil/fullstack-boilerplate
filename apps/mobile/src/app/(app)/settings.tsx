import { router } from "expo-router";
import { Platform, ScrollView, Text, View } from "react-native";

import { Button } from "@/components/button";
import { Screen } from "@/components/screen";
import { getRuntimeEnv } from "@/lib/env";
import { useTheme } from "@/theme/use-theme";

function Row({ label, value }: { label: string; value: string }) {
  const { colors, spacing, typography } = useTheme();
  return (
    <View
      accessible
      accessibilityLabel={`${label}: ${value}`}
      style={{
        paddingVertical: spacing.md,
        borderBottomWidth: 1,
        borderBottomColor: colors.border,
      }}
    >
      <Text style={[typography.label, { color: colors.textMuted }]}>{label}</Text>
      <Text selectable style={[typography.body, { color: colors.text }]}>
        {value}
      </Text>
    </View>
  );
}

export default function Settings() {
  const { colors, scheme, spacing, typography } = useTheme();
  const env = getRuntimeEnv();
  return (
    <Screen edges={["left", "right"]}>
      <ScrollView contentContainerStyle={{ padding: spacing.xl, gap: spacing.lg }}>
        <Text
          accessibilityRole="header"
          style={[typography.heading, { color: colors.text }]}
        >
          About this build
        </Text>
        <View>
          <Row label="Version" value={env.appVersion} />
          <Row label="Variant" value={env.appVariant} />
          <Row label="Platform" value={Platform.OS} />
          <Row label="API URL" value={env.apiUrl} />
          <Row label="Theme" value={`${scheme} (follows system)`} />
        </View>
        <Button
          title="Back to sign in"
          variant="secondary"
          onPress={() => router.replace("/sign-in")}
        />
      </ScrollView>
    </Screen>
  );
}

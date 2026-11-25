import Constants from "expo-constants";
import { Linking, Platform } from "react-native";

import { Button } from "@/components/button";
import { Screen } from "@/components/screen";
import { Body, Title } from "@/components/ui";
import { useTheme } from "@/theme/use-theme";

/** Replaces the whole app when the API answers 426: this build is too old. */
export function UpdateRequiredScreen({ minVersion }: { minVersion: string | null }) {
  const { spacing } = useTheme();
  const androidPackage = Constants.expoConfig?.android?.package;
  const storeUrl =
    Platform.OS === "android" && androidPackage
      ? `market://details?id=${androidPackage}`
      : null;
  return (
    <Screen style={{ padding: spacing.xl, gap: spacing.lg, justifyContent: "center" }}>
      <Title>Please update</Title>
      <Body>
        This version of the app is no longer supported
        {minVersion ? ` (version ${minVersion} or newer is required)` : ""}. Update it
        from the store to keep going.
      </Body>
      {storeUrl ? (
        <Button
          title="Open the store"
          onPress={() => void Linking.openURL(storeUrl).catch(() => undefined)}
        />
      ) : null}
    </Screen>
  );
}

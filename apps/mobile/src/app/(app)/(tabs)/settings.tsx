import { router } from "expo-router";
import { useEffect, useState } from "react";
import { Alert, Platform, ScrollView, Switch, View } from "react-native";

import { Button } from "@/components/button";
import { Screen } from "@/components/screen";
import { Body, ErrorText, Heading, Muted } from "@/components/ui";
import { useAuthActions } from "@/features/auth/use-auth-actions";
import { useProfile } from "@/features/auth/use-profile";
import { isBiometricAvailable, useAppLock } from "@/features/lock/app-lock";
import {
  getPushPermission,
  registerPushDevice,
  requestPushPermission,
  type PushPermission,
} from "@/features/push/push";
import { describeError } from "@/lib/api-error";
import { getRuntimeEnv } from "@/lib/env";
import { useServices } from "@/providers/services";
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
      <Muted>{label}</Muted>
      <Body selectable style={typography.body}>
        {value}
      </Body>
    </View>
  );
}

function SwitchRow({
  label,
  hint,
  value,
  onValueChange,
  disabled,
}: {
  label: string;
  hint?: string;
  value: boolean;
  onValueChange: (next: boolean) => void;
  disabled?: boolean;
}) {
  const { spacing } = useTheme();
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
      <View style={{ flex: 1 }}>
        <Body>{label}</Body>
        {hint ? <Muted>{hint}</Muted> : null}
      </View>
      <Switch
        accessibilityLabel={label}
        value={value}
        onValueChange={onValueChange}
        disabled={disabled}
      />
    </View>
  );
}

export default function Settings() {
  const { scheme, spacing } = useTheme();
  const env = getRuntimeEnv();
  const { api } = useServices();
  const { data: profile } = useProfile();
  const { signOut } = useAuthActions();
  const lock = useAppLock();
  const [biometrics, setBiometrics] = useState(true);
  const [push, setPush] = useState<PushPermission>("undetermined");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    isBiometricAvailable().then(setBiometrics, () => setBiometrics(false));
    getPushPermission().then(setPush, () => undefined);
  }, []);

  return (
    <Screen edges={["left", "right"]}>
      <ScrollView contentContainerStyle={{ padding: spacing.xl, gap: spacing.lg }}>
        <Heading>Account</Heading>
        <View>
          <Row label="Name" value={profile?.name ?? "…"} />
          <Row label="Email" value={profile?.email ?? "…"} />
        </View>
        <Button
          title="Profile"
          variant="secondary"
          onPress={() => router.push("/profile")}
        />
        <Button
          title="Sessions"
          variant="secondary"
          onPress={() => router.push("/sessions")}
        />

        <Heading>Security</Heading>
        <SwitchRow
          label="Unlock with biometrics"
          hint={
            biometrics
              ? "Ask for your fingerprint, face or device PIN when the app opens."
              : "Set up a fingerprint, face or screen lock on this device first."
          }
          value={lock.enabled}
          disabled={!biometrics && !lock.enabled}
          onValueChange={(next) => {
            setError(null);
            lock
              .setEnabled(next)
              .catch((caught: unknown) => setError(describeError(caught)));
          }}
        />

        <Heading>Notifications</Heading>
        <SwitchRow
          label="Push notifications"
          hint={
            push === "denied"
              ? "Blocked in system settings."
              : "Get a notification when something changes."
          }
          value={push === "granted"}
          disabled={push === "denied" || push === "granted"}
          onValueChange={() => {
            setError(null);
            requestPushPermission()
              .then(async (granted) => {
                setPush(await getPushPermission());
                if (granted) await registerPushDevice(api);
              })
              .catch((caught: unknown) => setError(describeError(caught)));
          }}
        />
        <ErrorText message={error} />

        <Heading>About this build</Heading>
        <View>
          <Row label="Version" value={env.appVersion} />
          <Row label="Variant" value={env.appVariant} />
          <Row label="Platform" value={Platform.OS} />
          <Row label="API URL" value={env.apiUrl} />
          <Row label="Theme" value={`${scheme} (follows system)`} />
        </View>

        <Button
          title="Sign out"
          onPress={() =>
            Alert.alert("Sign out?", "Unsynced changes on this device are discarded.", [
              { text: "Cancel", style: "cancel" },
              { text: "Sign out", style: "destructive", onPress: () => void signOut() },
            ])
          }
        />
        <Button
          title="Delete account"
          variant="secondary"
          onPress={() => router.push("/delete-account")}
        />
      </ScrollView>
    </Screen>
  );
}

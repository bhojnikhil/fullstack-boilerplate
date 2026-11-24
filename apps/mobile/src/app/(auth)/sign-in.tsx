import { Link, router } from "expo-router";
import { useHeaderHeight } from "expo-router/react-navigation";
import { useState } from "react";
import { Text } from "react-native";

import { Button } from "@/components/button";
import { KeyboardAvoidingForm } from "@/components/keyboard-avoiding-form";
import { Screen } from "@/components/screen";
import { TextField } from "@/components/text-field";
import { useTheme } from "@/theme/use-theme";

/** Placeholder: the form is not wired to the API until phase 9b. */
export default function SignIn() {
  const { colors, typography } = useTheme();
  const headerHeight = useHeaderHeight();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  return (
    <Screen edges={["bottom", "left", "right"]}>
      <KeyboardAvoidingForm keyboardVerticalOffset={headerHeight}>
        <Text
          accessibilityRole="header"
          style={[typography.title, { color: colors.text }]}
        >
          Welcome back
        </Text>
        <TextField
          label="Email"
          value={email}
          onChangeText={setEmail}
          autoCapitalize="none"
          autoComplete="email"
          keyboardType="email-address"
          textContentType="emailAddress"
          returnKeyType="next"
        />
        <TextField
          label="Password"
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          autoComplete="current-password"
          textContentType="password"
          returnKeyType="done"
        />
        <Button title="Sign in" disabled />
        <Text style={[typography.caption, { color: colors.textMuted }]}>
          Sign-in isn&apos;t connected to the API yet.
        </Text>
        <Link href="/sign-up" style={[typography.body, { color: colors.text }]}>
          Create an account
        </Link>
        <Button
          title="Preview app screens"
          variant="secondary"
          accessibilityHint="Opens the signed-in screens without an account. Placeholder until sign-in exists."
          // replace, not push: Android back from the app should exit, not
          // return to sign-in.
          onPress={() => router.replace("/items")}
        />
      </KeyboardAvoidingForm>
    </Screen>
  );
}

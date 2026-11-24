import { useHeaderHeight } from "expo-router/react-navigation";
import { useState } from "react";
import { Text } from "react-native";

import { Button } from "@/components/button";
import { KeyboardAvoidingForm } from "@/components/keyboard-avoiding-form";
import { Screen } from "@/components/screen";
import { TextField } from "@/components/text-field";
import { useDiscardChangesGuard } from "@/hooks/use-discard-changes-guard";
import { useTheme } from "@/theme/use-theme";

/** Placeholder: the form is not wired to the API until phase 9b. */
export default function SignUp() {
  const { colors, typography } = useTheme();
  const headerHeight = useHeaderHeight();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  // Android back (and header back / iOS swipe) asks before discarding input.
  useDiscardChangesGuard(name !== "" || email !== "" || password !== "");

  return (
    <Screen edges={["bottom", "left", "right"]}>
      <KeyboardAvoidingForm keyboardVerticalOffset={headerHeight}>
        <Text
          accessibilityRole="header"
          style={[typography.title, { color: colors.text }]}
        >
          Create your account
        </Text>
        <TextField
          label="Name"
          value={name}
          onChangeText={setName}
          autoComplete="name"
          textContentType="name"
          returnKeyType="next"
        />
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
          autoComplete="new-password"
          textContentType="newPassword"
          returnKeyType="done"
        />
        <Button title="Create account" disabled />
        <Text style={[typography.caption, { color: colors.textMuted }]}>
          Sign-up isn&apos;t connected to the API yet.
        </Text>
      </KeyboardAvoidingForm>
    </Screen>
  );
}

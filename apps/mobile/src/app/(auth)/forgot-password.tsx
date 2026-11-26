import { Link } from "expo-router";
import { useState } from "react";

import { Button } from "@/components/button";
import { KeyboardAvoidingForm } from "@/components/keyboard-avoiding-form";
import { Screen } from "@/components/screen";
import { TextField } from "@/components/text-field";
import { Body, ErrorText, Title } from "@/components/ui";
import { useSubmit } from "@/features/auth/use-submit";
import { unwrap } from "@/lib/api-error";
import { useServices } from "@/providers/services";
import { useTheme } from "@/theme/use-theme";

export default function ForgotPassword() {
  const { api } = useServices();
  const { colors, typography } = useTheme();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const request = useSubmit(async () => {
    await unwrap(
      api.POST("/v1/auth/password/forgot", { body: { email: email.trim() } }),
    );
    setSent(true);
  });

  return (
    <Screen edges={["bottom", "left", "right"]}>
      <KeyboardAvoidingForm>
        <Title>Reset your password</Title>
        {sent ? (
          <Body accessibilityLiveRegion="polite">
            If that address has an account, we sent a reset link. Open it on this phone.
          </Body>
        ) : (
          <>
            <TextField
              label="Email"
              value={email}
              onChangeText={setEmail}
              autoCapitalize="none"
              autoComplete="email"
              keyboardType="email-address"
              textContentType="emailAddress"
            />
            <ErrorText message={request.error} />
            <Button
              title={request.pending ? "Sending…" : "Send reset link"}
              disabled={request.pending || !email}
              onPress={() => void request.run()}
            />
          </>
        )}
        <Link href="/sign-in" style={[typography.body, { color: colors.text }]}>
          Back to sign in
        </Link>
      </KeyboardAvoidingForm>
    </Screen>
  );
}

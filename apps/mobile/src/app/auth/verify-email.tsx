import { router, useLocalSearchParams } from "expo-router";
import { useState } from "react";

import { Button } from "@/components/button";
import { KeyboardAvoidingForm } from "@/components/keyboard-avoiding-form";
import { Screen } from "@/components/screen";
import { TextField } from "@/components/text-field";
import { Body, ErrorText, Title } from "@/components/ui";
import { useSubmit } from "@/features/auth/use-submit";
import { ApiError, describeError, unwrap } from "@/lib/api-error";
import { useServices } from "@/providers/services";

/**
 * Deep link target of the verification email (…/auth/verify-email?token=…).
 * The API requires the password chosen at registration along with the token.
 */
export default function VerifyEmail() {
  const { token } = useLocalSearchParams<{ token?: string }>();
  const { api } = useServices();
  const [password, setPassword] = useState("");
  const [verified, setVerified] = useState(false);
  const verify = useSubmit(
    async () => {
      await unwrap(
        api.POST("/v1/auth/verify-email", { body: { token: token ?? "", password } }),
      );
      setPassword("");
      setVerified(true);
    },
    (error) =>
      error instanceof ApiError && error.status === 400
        ? "That link is invalid or has expired, or the password doesn't match. Request a new email from sign-in."
        : describeError(error),
  );

  return (
    <Screen edges={["bottom", "left", "right"]}>
      <KeyboardAvoidingForm>
        <Title>Verify your email</Title>
        {!token ? (
          <Body>This link is incomplete. Open the link from the email again.</Body>
        ) : verified ? (
          <>
            <Body accessibilityLiveRegion="polite">Your email is verified.</Body>
            <Button title="Go to sign in" onPress={() => router.replace("/sign-in")} />
          </>
        ) : (
          <>
            <Body>Enter the password you chose when you created your account.</Body>
            <TextField
              label="Password"
              value={password}
              onChangeText={setPassword}
              secureTextEntry
              autoComplete="current-password"
              textContentType="password"
            />
            <ErrorText message={verify.error} />
            <Button
              title={verify.pending ? "Verifying…" : "Verify email"}
              disabled={verify.pending || !password}
              onPress={() => void verify.run()}
            />
          </>
        )}
      </KeyboardAvoidingForm>
    </Screen>
  );
}

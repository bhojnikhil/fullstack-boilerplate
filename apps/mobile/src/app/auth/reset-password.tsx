import { router, useLocalSearchParams } from "expo-router";
import { useState } from "react";

import { Button } from "@/components/button";
import { KeyboardAvoidingForm } from "@/components/keyboard-avoiding-form";
import { Screen } from "@/components/screen";
import { TextField } from "@/components/text-field";
import { Body, ErrorText, Title } from "@/components/ui";
import { useSubmit } from "@/features/auth/use-submit";
import { useDiscardChangesGuard } from "@/hooks/use-discard-changes-guard";
import { ApiError, describeError, unwrap } from "@/lib/api-error";
import { useServices } from "@/providers/services";

/** Deep link target of the reset email (…/auth/reset-password?token=…). */
export default function ResetPassword() {
  const { token } = useLocalSearchParams<{ token?: string }>();
  const { api } = useServices();
  const [password, setPassword] = useState("");
  const [done, setDone] = useState(false);
  useDiscardChangesGuard(!done && password !== "", () => setPassword(""));
  const reset = useSubmit(
    async () => {
      await unwrap(
        api.POST("/v1/auth/password/reset", {
          body: { token: token ?? "", new_password: password },
        }),
      );
      setPassword("");
      setDone(true);
    },
    (error) =>
      error instanceof ApiError && error.code === "password_breached"
        ? "That password has appeared in a data breach. Choose another."
        : error instanceof ApiError && error.status === 400
          ? "This reset link is invalid or has expired. Request a new one."
          : describeError(error),
  );

  return (
    <Screen edges={["bottom", "left", "right"]}>
      <KeyboardAvoidingForm>
        <Title>Choose a new password</Title>
        {!token ? (
          <Body>This link is incomplete. Open the link from the email again.</Body>
        ) : done ? (
          <>
            <Body accessibilityLiveRegion="polite">
              Password changed. All your devices were signed out.
            </Body>
            <Button title="Go to sign in" onPress={() => router.replace("/sign-in")} />
          </>
        ) : (
          <>
            <TextField
              label="New password"
              value={password}
              onChangeText={setPassword}
              secureTextEntry
              autoComplete="new-password"
              textContentType="newPassword"
            />
            <ErrorText message={reset.error} />
            <Button
              title={reset.pending ? "Saving…" : "Change password"}
              disabled={reset.pending || !password}
              onPress={() => void reset.run()}
            />
          </>
        )}
      </KeyboardAvoidingForm>
    </Screen>
  );
}

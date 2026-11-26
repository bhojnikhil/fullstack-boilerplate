import { useState } from "react";

import { Button } from "@/components/button";
import { KeyboardAvoidingForm } from "@/components/keyboard-avoiding-form";
import { Screen } from "@/components/screen";
import { TextField } from "@/components/text-field";
import { Body, ErrorText, Heading } from "@/components/ui";
import { getGoogleIdToken, isGoogleSignInAvailable } from "@/features/auth/google";
import { useAuthActions } from "@/features/auth/use-auth-actions";
import { useProfile } from "@/features/auth/use-profile";
import { useSubmit } from "@/features/auth/use-submit";
import { ApiError, describeError, unwrap } from "@/lib/api-error";
import { useServices } from "@/providers/services";

function describeDeleteError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === "account_deletion_blocked") {
      return "You still own a workspace with other members. Transfer or delete it first.";
    }
    if (error.code === "reauthentication_failed")
      return "That didn't match. Try again.";
  }
  return describeError(error);
}

/** Deleting needs a fresh sign-in: the password (or Google) is checked first. */
export default function DeleteAccount() {
  const { api } = useServices();
  const { forgetLocally } = useAuthActions();
  const { data: profile } = useProfile();
  const [password, setPassword] = useState("");
  const hasPassword = profile?.sign_in_methods.includes("password") ?? true;
  const useGoogle = !hasPassword && isGoogleSignInAvailable();

  const remove = useSubmit(async () => {
    await unwrap(
      api.POST("/v1/auth/reauthenticate", {
        body: useGoogle ? { id_token: await getGoogleIdToken() } : { password },
      }),
    );
    await unwrap(api.DELETE("/v1/me"));
    setPassword("");
    await forgetLocally();
  }, describeDeleteError);

  return (
    <Screen edges={["bottom", "left", "right"]}>
      <KeyboardAvoidingForm>
        <Heading>Delete your account</Heading>
        <Body>
          This permanently deletes your account and signs you out everywhere. It
          can&apos;t be undone.
        </Body>
        {hasPassword ? (
          <TextField
            label="Confirm with your password"
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            autoComplete="current-password"
          />
        ) : null}
        <ErrorText message={remove.error} />
        <Button
          title={remove.pending ? "Deleting…" : "Delete my account"}
          disabled={
            remove.pending || (hasPassword && !password) || (!hasPassword && !useGoogle)
          }
          onPress={() => void remove.run()}
        />
      </KeyboardAvoidingForm>
    </Screen>
  );
}

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/button";
import { KeyboardAvoidingForm } from "@/components/keyboard-avoiding-form";
import { Screen } from "@/components/screen";
import { TextField } from "@/components/text-field";
import { Body, ErrorText, Heading, Muted } from "@/components/ui";
import { useProfile } from "@/features/auth/use-profile";
import { useSubmit } from "@/features/auth/use-submit";
import { useDiscardChangesGuard } from "@/hooks/use-discard-changes-guard";
import { ApiError, describeError, unwrap } from "@/lib/api-error";
import { useServices } from "@/providers/services";

export default function Profile() {
  const { api } = useServices();
  const queryClient = useQueryClient();
  const { data: profile } = useProfile();
  // null = untouched: show the saved name without copying it into state.
  const [edited, setName] = useState<string | null>(null);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [notice, setNotice] = useState<string | null>(null);

  const name = edited ?? profile?.name ?? "";
  const dirty =
    (edited !== null && edited !== profile?.name) || current !== "" || next !== "";
  useDiscardChangesGuard(dirty, () => {
    setName(null);
    setCurrent("");
    setNext("");
  });

  const saveName = useSubmit(async () => {
    await unwrap(api.PATCH("/v1/me", { body: { name: name.trim() } }));
    await queryClient.invalidateQueries({ queryKey: ["profile"] });
    setNotice("Name saved.");
  });
  const changePassword = useSubmit(
    async () => {
      await unwrap(
        api.POST("/v1/me/password", {
          body: { current_password: current, new_password: next },
        }),
      );
      setCurrent("");
      setNext("");
      setNotice("Password changed. Your other devices were signed out.");
    },
    (error) =>
      error instanceof ApiError && error.code === "password_breached"
        ? "That password has appeared in a data breach. Choose another."
        : describeError(error),
  );

  return (
    <Screen edges={["bottom", "left", "right"]}>
      <KeyboardAvoidingForm>
        <Heading>Profile</Heading>
        <Muted>{profile?.email}</Muted>
        {notice ? <Body accessibilityLiveRegion="polite">{notice}</Body> : null}
        <TextField
          label="Name"
          value={name}
          onChangeText={setName}
          autoComplete="name"
        />
        <ErrorText message={saveName.error} />
        <Button
          title="Save name"
          disabled={saveName.pending || !name.trim() || name === profile?.name}
          onPress={() => void saveName.run()}
        />
        {profile?.sign_in_methods.includes("password") ? (
          <>
            <Heading>Change password</Heading>
            <TextField
              label="Current password"
              value={current}
              onChangeText={setCurrent}
              secureTextEntry
              autoComplete="current-password"
            />
            <TextField
              label="New password"
              value={next}
              onChangeText={setNext}
              secureTextEntry
              autoComplete="new-password"
            />
            <ErrorText message={changePassword.error} />
            <Button
              title="Change password"
              disabled={changePassword.pending || !current || !next}
              onPress={() => void changePassword.run()}
            />
          </>
        ) : null}
      </KeyboardAvoidingForm>
    </Screen>
  );
}

import { useQueryClient } from "@tanstack/react-query";
import { router } from "expo-router";
import { useState } from "react";
import { Alert } from "react-native";
import { Button } from "@/components/button";
import { KeyboardAvoidingForm } from "@/components/keyboard-avoiding-form";
import { Screen } from "@/components/screen";
import { TextField } from "@/components/text-field";
import { Body, ErrorText } from "@/components/ui";
import { getGoogleIdToken, isGoogleSignInAvailable } from "@/features/auth/google";
import { useProfile } from "@/features/auth/use-profile";
import { useSubmit } from "@/features/auth/use-submit";
import {
  useActiveWorkspace,
  useWorkspaceClient,
} from "@/features/workspaces/use-workspaces";
import { unwrap } from "@/lib/api-error";
import { useServices } from "@/providers/services";

export default function WorkspaceManage() {
  const { active } = useActiveWorkspace();
  const client = useWorkspaceClient();
  const { api, workspaceId } = useServices();
  const query = useQueryClient();
  const { data: profile } = useProfile();
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const hasPassword = profile?.sign_in_methods.includes("password") ?? true;
  const reauthenticate = async () => {
    await unwrap(
      api.POST("/v1/auth/reauthenticate", {
        body: hasPassword ? { password } : { id_token: await getGoogleIdToken() },
      }),
    );
    setPassword("");
  };
  const action = useSubmit(async (kind: "rename" | "leave" | "delete") => {
    if (!active) return;
    if (kind === "rename") await client.rename(active.id, name.trim());
    if (kind === "leave") await client.leave(active.id);
    if (kind === "delete") {
      await reauthenticate();
      await client.delete(active.id);
    }
    if (kind !== "rename") workspaceId.set(null);
    await query.invalidateQueries({ queryKey: ["workspaces"] });
    if (kind !== "rename") router.replace("/workspaces");
  });
  if (!active)
    return (
      <Screen>
        <Body>Choose a workspace first.</Body>
      </Screen>
    );
  const owner = active.role === "owner";
  return (
    <Screen edges={["bottom", "left", "right"]}>
      <KeyboardAvoidingForm>
        <Body>{active.name}</Body>
        {active.role !== "member" ? (
          <>
            <TextField label="New name" value={name} onChangeText={setName} />
            <Button
              title="Rename"
              disabled={!name.trim() || action.pending}
              onPress={() => void action.run("rename")}
            />
          </>
        ) : null}
        {owner ? (
          <>
            <Body>
              Transfer ownership from the Members screen, or delete this workspace
              permanently.
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
            <Button
              title="Delete workspace"
              disabled={
                action.pending || (hasPassword ? !password : !isGoogleSignInAvailable())
              }
              onPress={() =>
                Alert.alert(
                  "Delete workspace?",
                  "This permanently deletes the workspace and its contents.",
                  [
                    { text: "Cancel", style: "cancel" },
                    {
                      text: "Delete",
                      style: "destructive",
                      onPress: () => void action.run("delete"),
                    },
                  ],
                )
              }
            />
          </>
        ) : (
          <Button
            title="Leave workspace"
            disabled={action.pending}
            onPress={() =>
              Alert.alert("Leave workspace?", "You will lose access.", [
                { text: "Cancel", style: "cancel" },
                {
                  text: "Leave",
                  style: "destructive",
                  onPress: () => void action.run("leave"),
                },
              ])
            }
          />
        )}
        <ErrorText message={action.error} />
      </KeyboardAvoidingForm>
    </Screen>
  );
}

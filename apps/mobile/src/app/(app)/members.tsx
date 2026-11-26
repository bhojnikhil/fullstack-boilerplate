import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Alert, FlatList, View } from "react-native";

import { Button } from "@/components/button";
import { TextField } from "@/components/text-field";
import { getGoogleIdToken, isGoogleSignInAvailable } from "@/features/auth/google";
import { useProfile } from "@/features/auth/use-profile";
import { Screen } from "@/components/screen";
import { Body, ErrorText, Muted } from "@/components/ui";
import {
  useActiveWorkspace,
  useWorkspaceClient,
} from "@/features/workspaces/use-workspaces";
import { describeError, unwrap } from "@/lib/api-error";
import { useServices, useSession } from "@/providers/services";
import { useTheme } from "@/theme/use-theme";

export default function Members() {
  const { spacing, colors } = useTheme();
  const { active } = useActiveWorkspace();
  const client = useWorkspaceClient();
  const queryClient = useQueryClient();
  const { accountId } = useSession();
  const { api } = useServices();
  const { data: profile } = useProfile();
  const [password, setPassword] = useState("");
  const hasPassword = profile?.sign_in_methods.includes("password") ?? true;
  const key = ["members", active?.id] as const;
  const members = useQuery({
    queryKey: key,
    enabled: active !== null,
    queryFn: () => client.members(active!.id),
  });
  const canManage = active?.role === "owner" || active?.role === "admin";

  if (!active) {
    return (
      <Screen style={{ padding: spacing.xl }}>
        <Body>Choose a workspace first.</Body>
      </Screen>
    );
  }
  return (
    <Screen edges={["bottom", "left", "right"]}>
      <FlatList
        data={members.data ?? []}
        keyExtractor={(member) => member.user_id}
        contentContainerStyle={{ padding: spacing.xl, gap: spacing.md }}
        ListHeaderComponent={
          members.error ? (
            <ErrorText message={describeError(members.error)} />
          ) : undefined
        }
        ListFooterComponent={
          active.role === "owner" && hasPassword ? (
            <TextField
              label="Password for ownership transfer"
              value={password}
              onChangeText={setPassword}
              secureTextEntry
              autoComplete="current-password"
            />
          ) : undefined
        }
        renderItem={({ item }) => (
          <View
            style={{
              borderBottomWidth: 1,
              borderBottomColor: colors.border,
              paddingBottom: spacing.md,
              gap: spacing.xs,
            }}
          >
            <Body>
              {item.name}
              {item.user_id === accountId ? " (you)" : ""}
            </Body>
            <Muted>
              {item.email ?? item.name} · {item.role}
            </Muted>
            {active.role === "owner" &&
            item.role !== "owner" &&
            item.user_id !== accountId ? (
              <>
                <Button
                  title={item.role === "admin" ? "Make member" : "Make admin"}
                  variant="secondary"
                  onPress={() =>
                    void client
                      .changeRole(
                        active.id,
                        item.user_id,
                        item.role === "admin" ? "member" : "admin",
                      )
                      .then(() => queryClient.invalidateQueries({ queryKey: key }))
                      .catch((error: unknown) =>
                        Alert.alert("Couldn't change role", describeError(error)),
                      )
                  }
                />
                <Button
                  title={`Transfer ownership to ${item.name}`}
                  variant="secondary"
                  disabled={hasPassword ? !password : !isGoogleSignInAvailable()}
                  onPress={() =>
                    Alert.alert(
                      "Transfer ownership?",
                      `${item.name} will become the owner.`,
                      [
                        { text: "Cancel", style: "cancel" },
                        {
                          text: "Transfer",
                          onPress: () =>
                            void (async () => {
                              await unwrap(
                                api.POST("/v1/auth/reauthenticate", {
                                  body: hasPassword
                                    ? { password }
                                    : { id_token: await getGoogleIdToken() },
                                }),
                              );
                              setPassword("");
                              await client.transfer(active.id, item.user_id);
                              await queryClient.invalidateQueries({
                                queryKey: ["workspaces"],
                              });
                              await queryClient.invalidateQueries({ queryKey: key });
                            })().catch((error: unknown) =>
                              Alert.alert("Couldn't transfer", describeError(error)),
                            ),
                        },
                      ],
                    )
                  }
                />
              </>
            ) : null}
            {canManage && item.role !== "owner" && item.user_id !== accountId ? (
              <Button
                title={`Remove ${item.name}`}
                variant="secondary"
                onPress={() =>
                  Alert.alert(
                    `Remove ${item.name}?`,
                    "They lose access to this workspace.",
                    [
                      { text: "Cancel", style: "cancel" },
                      {
                        text: "Remove",
                        style: "destructive",
                        onPress: () =>
                          client
                            .removeMember(active.id, item.user_id)
                            .then(() =>
                              queryClient.invalidateQueries({ queryKey: key }),
                            )
                            .catch((error: unknown) =>
                              Alert.alert("Couldn't remove", describeError(error)),
                            ),
                      },
                    ],
                  )
                }
              />
            ) : null}
          </View>
        )}
      />
    </Screen>
  );
}

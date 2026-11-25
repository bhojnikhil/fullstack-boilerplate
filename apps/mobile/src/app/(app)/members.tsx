import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, FlatList, View } from "react-native";

import { Button } from "@/components/button";
import { Screen } from "@/components/screen";
import { Body, ErrorText, Muted } from "@/components/ui";
import {
  useActiveWorkspace,
  useWorkspaceClient,
} from "@/features/workspaces/use-workspaces";
import { describeError } from "@/lib/api-error";
import { useSession } from "@/providers/services";
import { useTheme } from "@/theme/use-theme";

export default function Members() {
  const { spacing, colors } = useTheme();
  const { active } = useActiveWorkspace();
  const client = useWorkspaceClient();
  const queryClient = useQueryClient();
  const { accountId } = useSession();
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
              {item.email} · {item.role}
            </Muted>
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

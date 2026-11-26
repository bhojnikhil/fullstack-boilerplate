import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, FlatList, View } from "react-native";

import { Button } from "@/components/button";
import { Screen } from "@/components/screen";
import { Body, ErrorText, Muted } from "@/components/ui";
import { describeError, unwrap } from "@/lib/api-error";
import { useServices, useSession } from "@/providers/services";
import { useTheme } from "@/theme/use-theme";

export default function Sessions() {
  const { api } = useServices();
  const { accountId } = useSession();
  const queryClient = useQueryClient();
  const { spacing, colors } = useTheme();
  const key = ["sessions", accountId];
  const sessions = useQuery({
    queryKey: key,
    queryFn: () => unwrap(api.GET("/v1/auth/sessions")),
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: key });
  const fail = (error: unknown) =>
    Alert.alert("Couldn't update sessions", describeError(error));

  return (
    <Screen edges={["bottom", "left", "right"]}>
      <FlatList
        data={sessions.data?.items ?? []}
        keyExtractor={(session) => session.id}
        contentContainerStyle={{ padding: spacing.xl, gap: spacing.md }}
        ListHeaderComponent={
          <View style={{ gap: spacing.md }}>
            {sessions.error ? (
              <ErrorText message={describeError(sessions.error)} />
            ) : null}
            <Button
              title="Sign out all other devices"
              variant="secondary"
              onPress={() =>
                unwrap(api.POST("/v1/auth/sessions/revoke-others")).then(refresh, fail)
              }
            />
          </View>
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
              {item.device_name ?? item.platform}
              {item.current ? " (this device)" : ""}
            </Body>
            <Muted>
              {item.sign_in_method} · last used{" "}
              {new Date(item.last_used_at).toLocaleString()}
            </Muted>
            {!item.current ? (
              <Button
                title={`Sign out ${item.device_name ?? item.platform}`}
                variant="secondary"
                onPress={() =>
                  unwrap(
                    api.DELETE("/v1/auth/sessions/{session_id}", {
                      params: { path: { session_id: item.id } },
                    }),
                  ).then(refresh, fail)
                }
              />
            ) : null}
          </View>
        )}
      />
    </Screen>
  );
}

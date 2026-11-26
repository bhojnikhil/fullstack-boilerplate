import { router } from "expo-router";
import { ActivityIndicator, Pressable, ScrollView, Text, View } from "react-native";

import { Button } from "@/components/button";
import { Screen } from "@/components/screen";
import { Body, ErrorText, Heading, Muted } from "@/components/ui";
import { useWorkspaces } from "@/features/workspaces/use-workspaces";
import { describeError } from "@/lib/api-error";
import { useActiveWorkspaceId, useServices } from "@/providers/services";
import { MIN_TOUCH_TARGET } from "@/theme/tokens";
import { useTheme } from "@/theme/use-theme";

export default function Workspaces() {
  const { colors, spacing, radius, typography } = useTheme();
  const { workspaceId } = useServices();
  const active = useActiveWorkspaceId();
  const { data, isPending, error } = useWorkspaces();

  return (
    <Screen edges={["left", "right"]}>
      <ScrollView contentContainerStyle={{ padding: spacing.xl, gap: spacing.lg }}>
        <Heading>Your workspaces</Heading>
        {isPending ? (
          <ActivityIndicator accessibilityLabel="Loading" color={colors.text} />
        ) : null}
        {error ? <ErrorText message={describeError(error)} /> : null}
        {data?.length === 0 ? (
          <Body>You don&apos;t belong to a workspace yet.</Body>
        ) : null}
        {data?.map((workspace) => {
          const selected = workspace.id === active;
          return (
            <Pressable
              key={workspace.id}
              accessibilityRole="radio"
              accessibilityState={{ selected }}
              accessibilityLabel={`${workspace.name}, ${workspace.role}${selected ? ", current" : ""}`}
              onPress={() => workspaceId.set(workspace.id)}
              style={{
                minHeight: MIN_TOUCH_TARGET,
                padding: spacing.lg,
                borderRadius: radius.md,
                borderWidth: selected ? 2 : 1,
                borderColor: selected ? colors.primary : colors.controlBorder,
                backgroundColor: colors.surface,
                gap: spacing.xs,
              }}
            >
              <Text style={[typography.body, { color: colors.text }]}>
                {workspace.name}
              </Text>
              <Muted>
                {workspace.role}
                {selected ? " · current" : ""}
              </Muted>
            </Pressable>
          );
        })}
        <View style={{ gap: spacing.md }}>
          <Button
            title="Create a workspace"
            onPress={() => router.push("/workspace-new")}
          />
          <Button
            title="Manage workspace"
            variant="secondary"
            disabled={!active}
            onPress={() => router.push("/workspace-manage")}
          />
          <Button
            title="Members"
            variant="secondary"
            disabled={!active}
            onPress={() => router.push("/members")}
          />
          <Button
            title="Invite people"
            variant="secondary"
            disabled={!active}
            onPress={() => router.push("/invite-share")}
          />
        </View>
      </ScrollView>
    </Screen>
  );
}

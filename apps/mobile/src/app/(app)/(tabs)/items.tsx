import { router } from "expo-router";
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  RefreshControl,
  Text,
  View,
} from "react-native";

import { Button } from "@/components/button";
import { Screen } from "@/components/screen";
import { Body, ErrorText, Heading, Muted } from "@/components/ui";
import { useQueueFailures, useMutationQueue } from "@/features/items/queue-provider";
import { useItems, type DisplayItem } from "@/features/items/use-items";
import { PushPrompt } from "@/features/push/push-prompt";
import { describeError } from "@/lib/api-error";
import { MIN_TOUCH_TARGET } from "@/theme/tokens";
import { useTheme } from "@/theme/use-theme";

function ItemRow({ item }: { item: DisplayItem }) {
  const { colors, spacing, typography } = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${item.title}${item.pending ? ", not synced yet" : ""}`}
      accessibilityHint="Opens the item to edit it"
      onPress={() => router.push({ pathname: "/item/[id]", params: { id: item.id } })}
      style={{
        minHeight: MIN_TOUCH_TARGET,
        paddingVertical: spacing.md,
        borderBottomWidth: 1,
        borderBottomColor: colors.border,
        gap: spacing.xs,
      }}
    >
      <Text style={[typography.body, { color: colors.text }]}>{item.title}</Text>
      {item.description ? (
        <Text
          numberOfLines={2}
          style={[typography.caption, { color: colors.textMuted }]}
        >
          {item.description}
        </Text>
      ) : null}
      {item.pending ? (
        <Text style={[typography.caption, { color: colors.textMuted }]}>
          Waiting to sync
        </Text>
      ) : null}
    </Pressable>
  );
}

export default function Items() {
  const { spacing, colors } = useTheme();
  const { items, isPending, isRefetching, isError, error, refetch } = useItems();
  const failures = useQueueFailures();
  const queue = useMutationQueue();

  return (
    <Screen edges={["left", "right"]}>
      <FlatList
        testID="items-list"
        data={items}
        keyExtractor={(item) => item.id}
        contentContainerStyle={{ flexGrow: 1, padding: spacing.xl, gap: spacing.xs }}
        refreshControl={
          <RefreshControl
            refreshing={isRefetching}
            onRefresh={() => void refetch()}
            tintColor={colors.text}
          />
        }
        ListHeaderComponent={
          <View style={{ gap: spacing.md, marginBottom: spacing.md }}>
            <Button title="New item" onPress={() => router.push("/item/new")} />
            {failures.length > 0 ? (
              <View accessibilityRole="alert" style={{ gap: spacing.sm }}>
                <ErrorText
                  message={`${failures.length} change${failures.length === 1 ? "" : "s"} couldn't be saved: ${failures[0]?.reason}`}
                />
                <Button
                  title="Dismiss"
                  variant="secondary"
                  onPress={() => queue.dismissFailures()}
                />
              </View>
            ) : null}
            {isError ? <ErrorText message={describeError(error)} /> : null}
            <PushPrompt />
          </View>
        }
        renderItem={({ item }) => <ItemRow item={item} />}
        ListEmptyComponent={
          isPending ? (
            <ActivityIndicator accessibilityLabel="Loading items" color={colors.text} />
          ) : (
            <View
              style={{
                flex: 1,
                justifyContent: "center",
                alignItems: "center",
                gap: spacing.sm,
              }}
            >
              <Heading>No items yet</Heading>
              <Body>Add your first item. It syncs when you&apos;re online.</Body>
              <Muted>Pull down to refresh.</Muted>
            </View>
          )
        }
      />
    </Screen>
  );
}

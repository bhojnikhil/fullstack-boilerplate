import { Stack } from "expo-router";

import { QueueProvider } from "@/features/items/queue-provider";
import { usePushLifecycle } from "@/features/push/use-push";

export const unstable_settings = { anchor: "(tabs)" };

/** Signed-in area: the tabs, plus detail screens pushed on top of them. */
export default function AppLayout() {
  usePushLifecycle();
  return (
    <QueueProvider>
      <Stack>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="item/new" options={{ title: "New item" }} />
        <Stack.Screen name="item/[id]" options={{ title: "Edit item" }} />
        <Stack.Screen name="workspace-new" options={{ title: "New workspace" }} />
        <Stack.Screen name="members" options={{ title: "Members" }} />
        <Stack.Screen name="invite-share" options={{ title: "Invite people" }} />
        <Stack.Screen name="profile" options={{ title: "Profile" }} />
        <Stack.Screen name="sessions" options={{ title: "Sessions" }} />
        <Stack.Screen name="delete-account" options={{ title: "Delete account" }} />
      </Stack>
    </QueueProvider>
  );
}

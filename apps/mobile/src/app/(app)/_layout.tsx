import { Stack, router } from "expo-router";

import { QueueProvider } from "@/features/items/queue-provider";
import { useEffect } from "react";
import { useServices } from "@/providers/services";
import { usePushLifecycle } from "@/features/push/use-push";

export const unstable_settings = { anchor: "(tabs)" };

/** Signed-in area: the tabs, plus detail screens pushed on top of them. */
export default function AppLayout() {
  usePushLifecycle();
  const { removedWorkspace } = useServices();
  useEffect(
    () =>
      removedWorkspace.subscribe(() => {
        if (removedWorkspace.get()) {
          removedWorkspace.set(null);
          router.replace("/workspaces");
        }
      }),
    [removedWorkspace],
  );
  return (
    <QueueProvider>
      <Stack>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="item/new" options={{ title: "New item" }} />
        <Stack.Screen name="item/[id]" options={{ title: "Edit item" }} />
        <Stack.Screen name="workspace-new" options={{ title: "New workspace" }} />
        <Stack.Screen name="workspace-manage" options={{ title: "Manage workspace" }} />
        <Stack.Screen name="members" options={{ title: "Members" }} />
        <Stack.Screen name="invite-share" options={{ title: "Invite people" }} />
        <Stack.Screen name="profile" options={{ title: "Profile" }} />
        <Stack.Screen name="sessions" options={{ title: "Sessions" }} />
        <Stack.Screen name="delete-account" options={{ title: "Delete account" }} />
      </Stack>
    </QueueProvider>
  );
}

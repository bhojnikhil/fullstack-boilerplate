import { router } from "expo-router";
import * as Notifications from "expo-notifications";
import { useEffect } from "react";

import { useServices, useSession } from "@/providers/services";

import { registerPushDevice, routeFromNotificationData } from "./push";

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: false,
    shouldSetBadge: false,
  }),
});

/**
 * Signed-in housekeeping: re-registers the push token when permission was
 * already granted (tokens change; `last_seen` stays fresh), and routes
 * notification taps. It never prompts; see PushPrompt for that.
 */
export function usePushLifecycle(): void {
  const { api } = useServices();
  const { status } = useSession();

  useEffect(() => {
    if (status !== "signedIn") return;
    registerPushDevice(api).catch(() => undefined);
  }, [api, status]);

  useEffect(() => {
    if (status !== "signedIn") return;
    const open = (response: Notifications.NotificationResponse | null | undefined) => {
      const route = routeFromNotificationData(
        response?.notification.request.content.data,
      );
      if (route) router.push(route as never);
    };
    // Cold start from a notification, then taps while running.
    Notifications.getLastNotificationResponseAsync()
      .then(open)
      .catch(() => undefined);
    const subscription = Notifications.addNotificationResponseReceivedListener(open);
    return () => subscription.remove();
  }, [status]);
}

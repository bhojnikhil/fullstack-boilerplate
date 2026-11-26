import Constants from "expo-constants";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { AndroidImportance } from "expo-notifications";
import { Platform } from "react-native";

import { unwrap } from "@/lib/api-error";
import { getClientHeaders } from "@/lib/client-headers";
import type { AppServices } from "@/lib/app-services";

type Api = AppServices["api"];

export type PushPermission = "granted" | "denied" | "undetermined";

export async function getPushPermission(): Promise<PushPermission> {
  const { status, canAskAgain } = await Notifications.getPermissionsAsync();
  if (status === "granted") return "granted";
  return status === "denied" && !canAskAgain ? "denied" : "undetermined";
}

/** Asks the OS for notification permission (call it from a user action). */
export async function requestPushPermission(): Promise<boolean> {
  if (Platform.OS === "android") {
    // Android 13+ shows the prompt only once a channel exists.
    await Notifications.setNotificationChannelAsync("default", {
      name: "Default",
      importance: AndroidImportance.DEFAULT,
    });
  }
  const { status } = await Notifications.requestPermissionsAsync();
  return status === "granted";
}

async function getExpoToken(): Promise<string | null> {
  // Push tokens exist only on physical devices.
  if (!Device.isDevice) return null;
  const projectId = (
    Constants.expoConfig?.extra as { eas?: { projectId?: string } } | undefined
  )?.eas?.projectId;
  if (!projectId) return null; // `eas init` has not been run: no push without a project.
  return (await Notifications.getExpoPushTokenAsync({ projectId })).data;
}

/** Registers this installation's Expo push token with the API. Idempotent. */
export async function registerPushDevice(api: Api): Promise<boolean> {
  if ((await getPushPermission()) !== "granted") return false;
  const token = await getExpoToken();
  if (!token) return false;
  const headers = getClientHeaders();
  await unwrap(
    api.POST("/v1/devices", {
      body: {
        expo_push_token: token,
        platform: headers["X-Platform"],
        app_version: headers["X-App-Version"],
      },
    }),
  );
  return true;
}

/** Stops pushes to this device (sign-out). Never prompts; no-ops without permission. */
export async function unregisterPushDevice(api: Api): Promise<void> {
  if ((await getPushPermission()) !== "granted") return;
  const token = await getExpoToken();
  if (!token) return;
  await api.DELETE("/v1/devices", { body: { expo_push_token: token } });
}

/**
 * Notification taps may carry `data.url`. Only in-app paths on an allowlist
 * are followed: a push payload must not be able to open arbitrary routes.
 */
const ROUTE_ALLOWLIST: readonly RegExp[] = [
  /^\/items$/,
  /^\/item\/[0-9a-f-]{36}$/i,
  /^\/workspaces$/,
  /^\/members$/,
  /^\/sessions$/,
];

export function routeFromNotificationData(data: unknown): string | null {
  const url = (data as { url?: unknown } | null | undefined)?.url;
  if (typeof url !== "string") return null;
  return ROUTE_ALLOWLIST.some((pattern) => pattern.test(url)) ? url : null;
}

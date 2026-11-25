import Constants from "expo-constants";
import { Platform } from "react-native";

/**
 * Header values the API uses for its minimum-app-version gate (426 when the
 * app is too old). Not sent anywhere yet: the generated API client (phase 9b)
 * will attach them to every request.
 */
export type ClientPlatform = "android" | "ios";

export interface ClientHeaders {
  "X-App-Version": string;
  "X-Platform": ClientPlatform;
}

const VERSION_RE = /^\d+\.\d+\.\d+$/;

export function buildClientHeaders(input: {
  appVersion: string | null | undefined;
  platform: string;
}): ClientHeaders {
  const { appVersion, platform } = input;
  if (platform !== "android" && platform !== "ios") {
    throw new Error(`Unsupported platform for API headers: ${platform}`);
  }
  if (!appVersion || !VERSION_RE.test(appVersion)) {
    throw new Error(`App version must be MAJOR.MINOR.PATCH, got ${String(appVersion)}`);
  }
  return { "X-App-Version": appVersion, "X-Platform": platform };
}

/**
 * Uses the app config version, i.e. the store version of the binary: with
 * runtimeVersion policy "appVersion", OTA updates only reach binaries of the
 * same version, so this always matches the installed build.
 */
export function getClientHeaders(): ClientHeaders {
  return buildClientHeaders({
    appVersion: Constants.expoConfig?.version,
    platform: Platform.OS,
  });
}

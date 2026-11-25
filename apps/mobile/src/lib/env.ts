import Constants from "expo-constants";

import type { AppExtra } from "../../app.config";

export type AppVariant = "development" | "preview" | "production";

/** Runtime view of the values app.config.ts resolved at build time. */
export interface RuntimeEnv {
  apiUrl: string;
  appVariant: AppVariant;
  appVersion: string;
  appDomain: string | undefined;
  /** Read but not wired to Sentry yet. */
  sentryDsn: string | undefined;
}

interface ExpoConfigLike {
  version?: string;
  extra?: Partial<AppExtra> | Record<string, unknown>;
}

const VARIANTS: readonly string[] = ["development", "preview", "production"];

function optionalString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

/** Validates `Constants.expoConfig`; throws if app.config.ts did not run. */
export function readRuntimeEnv(
  expoConfig: ExpoConfigLike | null | undefined,
): RuntimeEnv {
  const extra = (expoConfig?.extra ?? {}) as Record<string, unknown>;
  const apiUrl = optionalString(extra.apiUrl);
  const appVariant = optionalString(extra.appVariant);
  const appVersion = optionalString(expoConfig?.version);
  if (!apiUrl || !appVariant || !VARIANTS.includes(appVariant) || !appVersion) {
    throw new Error(
      "App config is missing apiUrl/appVariant/version; is app.config.ts being used?",
    );
  }
  return {
    apiUrl,
    appVariant: appVariant as AppVariant,
    appVersion,
    appDomain: optionalString(extra.appDomain),
    sentryDsn: optionalString(extra.sentryDsn),
  };
}

let cached: RuntimeEnv | undefined;

export function getRuntimeEnv(): RuntimeEnv {
  cached ??= readRuntimeEnv(Constants.expoConfig);
  return cached;
}

import type { ConfigContext, ExpoConfig } from "expo/config";

/**
 * Build-time environment.
 *
 * Kept in this file because Expo's config loader transpiles app.config.ts
 * but not local TypeScript imports; exported for unit tests. Every value is
 * validated here, so a bad value fails config evaluation (expo start, EAS
 * Build, expo-doctor) instead of producing a broken binary.
 *
 * Expo CLI loads apps/mobile/.env into process.env before evaluating the
 * config; EAS Build injects the profile `env` from eas.json plus EAS
 * environment variables. See apps/mobile/.env.example for every variable.
 */

export const APP_VARIANTS = ["development", "preview", "production"] as const;
export type AppVariant = (typeof APP_VARIANTS)[number];

/** Path prefixes the app claims as Android App Links (iOS paths live in the
 * server-side apple-app-site-association file). Screens for these arrive with
 * the auth/workspace flows; keep in sync with the web app's routes. */
export const APP_LINK_PATH_PREFIXES = ["/verify-email", "/reset-password", "/invite"];

export interface AppEnv {
  variant: AppVariant;
  name: string;
  slug: string;
  owner: string | undefined;
  scheme: string;
  androidPackage: string;
  iosBundleId: string;
  apiUrl: string;
  /** Bare host (no scheme) for Android App Links / iOS universal links. */
  appDomain: string | undefined;
  easProjectId: string | undefined;
  /** Read and exposed to the app; not wired to Sentry yet. */
  sentryDsn: string | undefined;
}

type Env = Record<string, string | undefined>;

const DEFAULTS = {
  name: "Boilerplate",
  slug: "fullstack-boilerplate",
  scheme: "boilerplate",
  androidPackage: "com.example.boilerplate",
  iosBundleId: "com.example.boilerplate",
  devApiUrl: "http://localhost:8000",
} as const;

// Reverse-DNS id: at least two segments, each starting with a letter.
const APP_ID_RE = /^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$/;
// URL scheme as accepted by Expo's `scheme` field.
const SCHEME_RE = /^[a-z][a-z0-9+.-]*$/;
// Bare hostname, e.g. app.example.com (no scheme, path or port).
const DOMAIN_RE = /^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$/i;
const SLUG_RE = /^[a-z0-9-]+$/;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function read(env: Env, key: string): string | undefined {
  const value = env[key]?.trim();
  return value ? value : undefined;
}

function invalid(key: string, value: string, expected: string): Error {
  return new Error(`Invalid ${key}=${JSON.stringify(value)}: expected ${expected}.`);
}

function check(key: string, value: string, re: RegExp, expected: string): string {
  if (!re.test(value)) throw invalid(key, value, expected);
  return value;
}

function parseVariant(env: Env): AppVariant {
  const raw = read(env, "APP_VARIANT") ?? "development";
  if (!(APP_VARIANTS as readonly string[]).includes(raw)) {
    throw invalid("APP_VARIANT", raw, APP_VARIANTS.join(" | "));
  }
  return raw as AppVariant;
}

function parseApiUrl(env: Env, variant: AppVariant): string {
  const raw = read(env, "API_URL");
  if (!raw) {
    if (variant === "development") return DEFAULTS.devApiUrl;
    throw new Error(`API_URL is required when APP_VARIANT=${variant}.`);
  }
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw invalid("API_URL", raw, "an absolute http(s) URL");
  }
  if (url.protocol !== "https:" && url.protocol !== "http:") {
    throw invalid("API_URL", raw, "an absolute http(s) URL");
  }
  if (variant !== "development" && url.protocol !== "https:") {
    throw invalid("API_URL", raw, `an https:// URL when APP_VARIANT=${variant}`);
  }
  // Normalise: no trailing slash, so callers can append "/v1/...".
  return raw.replace(/\/+$/, "");
}

/** Side-by-side installs: non-production variants get their own id/scheme. */
function suffixFor(variant: AppVariant): string {
  return variant === "production"
    ? ""
    : `.${variant === "development" ? "dev" : "preview"}`;
}

export function parseAppEnv(env: Env): AppEnv {
  const variant = parseVariant(env);
  const suffix = suffixFor(variant);
  const nameSuffix = { development: " (Dev)", preview: " (Preview)", production: "" }[
    variant
  ];

  const androidPackage = check(
    "ANDROID_PACKAGE",
    read(env, "ANDROID_PACKAGE") ?? DEFAULTS.androidPackage,
    APP_ID_RE,
    "a reverse-DNS id like com.example.app",
  );
  const iosBundleId = check(
    "IOS_BUNDLE_ID",
    read(env, "IOS_BUNDLE_ID") ?? DEFAULTS.iosBundleId,
    APP_ID_RE,
    "a reverse-DNS id like com.example.app",
  );
  const scheme = check(
    "APP_SCHEME",
    read(env, "APP_SCHEME") ?? DEFAULTS.scheme,
    SCHEME_RE,
    "lowercase letters, digits, '+', '.', '-', starting with a letter",
  );
  const slug = check(
    "APP_SLUG",
    read(env, "APP_SLUG") ?? DEFAULTS.slug,
    SLUG_RE,
    "lowercase letters, digits and '-'",
  );
  const appDomainRaw = read(env, "APP_DOMAIN");
  const easProjectIdRaw = read(env, "EAS_PROJECT_ID");

  return {
    variant,
    name: `${read(env, "APP_NAME") ?? DEFAULTS.name}${nameSuffix}`,
    slug,
    owner: read(env, "EXPO_OWNER"),
    scheme: `${scheme}${suffix.replace(".", "-")}`,
    androidPackage: `${androidPackage}${suffix}`,
    iosBundleId: `${iosBundleId}${suffix}`,
    apiUrl: parseApiUrl(env, variant),
    appDomain: appDomainRaw
      ? check("APP_DOMAIN", appDomainRaw, DOMAIN_RE, "a bare host like app.example.com")
      : undefined,
    easProjectId: easProjectIdRaw
      ? check("EAS_PROJECT_ID", easProjectIdRaw, UUID_RE, "a UUID")
      : undefined,
    sentryDsn: read(env, "SENTRY_DSN"),
  };
}

/** Values the app reads at runtime via Constants.expoConfig.extra (src/lib/env.ts). */
export interface AppExtra {
  apiUrl: string;
  appVariant: string;
  appDomain?: string;
  sentryDsn?: string;
  eas: { projectId?: string };
}

/** User-facing version. With `runtimeVersion.policy: "appVersion"`, EAS Update
 * only delivers updates to binaries with the same version. Build numbers
 * (versionCode / buildNumber) are managed remotely by EAS (see eas.json). */
const APP_VERSION = "1.0.0";

export default ({ config }: ConfigContext): ExpoConfig => {
  const env = parseAppEnv(process.env);

  const extra: AppExtra = {
    apiUrl: env.apiUrl,
    appVariant: env.variant,
    ...(env.appDomain ? { appDomain: env.appDomain } : {}),
    ...(env.sentryDsn ? { sentryDsn: env.sentryDsn } : {}),
    eas: env.easProjectId ? { projectId: env.easProjectId } : {},
  };

  return {
    ...config,
    name: env.name,
    slug: env.slug,
    ...(env.owner ? { owner: env.owner } : {}),
    version: APP_VERSION,
    platforms: ["ios", "android"],
    orientation: "portrait",
    scheme: env.scheme,
    // Follows the OS light/dark setting (needs expo-system-ui on Android).
    userInterfaceStyle: "automatic",
    runtimeVersion: { policy: "appVersion" },
    ...(env.easProjectId
      ? { updates: { url: `https://u.expo.dev/${env.easProjectId}` } }
      : {}),
    ios: {
      ...config.ios,
      bundleIdentifier: env.iosBundleId,
      supportsTablet: false,
      ...(env.appDomain ? { associatedDomains: [`applinks:${env.appDomain}`] } : {}),
    },
    android: {
      ...config.android,
      package: env.androidPackage,
      // Edge-to-edge is always on for Expo SDK 54+ apps (and enforced by
      // Android 15+ when targeting API 35); screens pad with safe-area insets.
      // Predictive back stays off so BackHandler listeners keep working.
      predictiveBackGestureEnabled: false,
      ...(env.appDomain
        ? {
            intentFilters: [
              {
                action: "VIEW",
                autoVerify: true,
                data: APP_LINK_PATH_PREFIXES.map((pathPrefix) => ({
                  scheme: "https",
                  host: env.appDomain,
                  pathPrefix,
                })),
                category: ["BROWSABLE", "DEFAULT"],
              },
            ],
          }
        : {}),
    },
    plugins: ["expo-router", "expo-secure-store"],
    extra,
  };
};

import type { ConfigContext, ExpoConfig } from "expo/config";

/**
 * Build-time environment.
 *
 * Kept in this file because Expo's config loader transpiles app.config.ts
 * but not local TypeScript imports; exported for unit tests. Every value is
 * validated here, so a bad value fails config evaluation (expo start, EAS
 * Build, EAS Update, expo-doctor) instead of producing a broken binary or
 * update. Error messages name the variable but never echo its value: config
 * values can carry credentials by mistake and errors end up in CI logs.
 *
 * Where values come from:
 * - Local Expo CLI: process env, then apps/mobile/.env (see .env.example).
 * - EAS CLI (`eas build`, `eas update`, `eas init`, ...): only the invoking
 *   shell's env (EAS CLI disables .env loading) plus, for `--environment`
 *   and on build workers, the EAS environment variables. See the README's
 *   "EAS" section for the required preflight exports.
 */

export const APP_VARIANTS = ["development", "preview", "production"] as const;
export type AppVariant = (typeof APP_VARIANTS)[number];

/**
 * User-facing version. Build numbers (versionCode / buildNumber) are managed
 * remotely by EAS (eas.json `appVersionSource: "remote"`).
 */
export const APP_VERSION = "1.0.0";

/**
 * Web pages that must always open in the browser (served by apps/web): store
 * listings and Play policy links point at them. App links may never claim them.
 */
export const RESERVED_WEB_PATHS = [
  "/privacy",
  "/terms",
  "/account-deletion",
  "/.well-known",
];

/**
 * Permissions that Expo's template or libraries add but this app doesn't use.
 * Expo writes them with tools:node="remove", which also strips them from
 * library manifests during the Gradle merge. Remove an entry before using
 * the feature that needs it.
 */
export const BLOCKED_ANDROID_PERMISSIONS = [
  "android.permission.SYSTEM_ALERT_WINDOW",
  "android.permission.VIBRATE",
  "android.permission.READ_EXTERNAL_STORAGE",
  "android.permission.WRITE_EXTERNAL_STORAGE",
];

/** An App Link path: exact (`/verify-email`) or a whole-segment prefix (`/invite/`). */
export interface AppLinkPath {
  kind: "exact" | "prefix";
  path: string;
}

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
  /** Paths the app claims on appDomain; empty means no app links at all. */
  appLinkPaths: AppLinkPath[];
  easProjectId: string | undefined;
  /** Read and exposed to the app; lib/sentry.ts starts Sentry when set. */
  sentryDsn: string | undefined;
  /** Public OAuth client ids (not secrets) for native Google sign-in. */
  googleWebClientId: string | undefined;
  googleIosClientId: string | undefined;
}

type Env = Record<string, string | undefined>;

/**
 * Every environment variable this config reads: the app settings plus the
 * EAS context markers. `read()` only accepts these names, so the list stays
 * complete. Tests and the release script strip them from the inherited
 * environment so a developer's shell can't leak into a test or a release.
 */
export const APP_CONFIG_ENV_KEYS = [
  "APP_VARIANT",
  "API_URL",
  "APP_NAME",
  "APP_SLUG",
  "EXPO_OWNER",
  "ANDROID_PACKAGE",
  "IOS_BUNDLE_ID",
  "APP_SCHEME",
  "APP_DOMAIN",
  "APP_LINK_PATHS",
  "EAS_PROJECT_ID",
  "SENTRY_DSN",
  "GOOGLE_WEB_CLIENT_ID",
  "GOOGLE_IOS_CLIENT_ID",
  "EAS_BUILD",
  "EAS_BUILD_PROFILE",
  "EXPO_NO_DOTENV",
] as const;
export type AppConfigEnvKey = (typeof APP_CONFIG_ENV_KEYS)[number];

/** A copy of `env` without any of APP_CONFIG_ENV_KEYS. */
export function withoutAppConfigEnv<T extends Env>(env: T): T {
  const copy: T = { ...env };
  for (const key of APP_CONFIG_ENV_KEYS) delete copy[key];
  return copy;
}

const DEFAULTS = {
  name: "Boilerplate",
  slug: "fullstack-boilerplate",
  scheme: "boilerplate",
  androidPackage: "com.example.boilerplate",
  iosBundleId: "com.example.boilerplate",
  devApiUrl: "http://localhost:8000",
} as const;

// Android application id: 2+ segments, each a letter then letters/digits/_.
const ANDROID_PACKAGE_RE = /^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$/;
// iOS bundle id: 2+ segments of letters, digits and hyphens (no underscores).
const IOS_BUNDLE_ID_RE = /^[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)+$/;
// The template's placeholder namespace; Google Play rejects com.example.*.
const PLACEHOLDER_ID_RE = /^com\.example(\.|$)/i;
// URL scheme as accepted by Expo's `scheme` field.
const SCHEME_RE = /^[a-z][a-z0-9+.-]*$/;
// Bare hostname, e.g. app.example.com (no scheme, path or port).
const DOMAIN_RE = /^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$/i;
// One or more path segments of unreserved URL characters; optional trailing
// slash (= segment-bounded prefix). No wildcards, no bare "/".
const APP_LINK_PATH_RE = /^(\/[A-Za-z0-9._~-]+)+\/?$/;
const SLUG_RE = /^[a-z0-9-]+$/;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function read(env: Env, key: AppConfigEnvKey): string | undefined {
  const value = env[key]?.trim();
  return value ? value : undefined;
}

function isTruthy(value: string | undefined): boolean {
  return (
    value !== undefined && !["0", "false", "no", "off"].includes(value.toLowerCase())
  );
}

function invalid(key: string, expected: string): Error {
  return new Error(`Invalid ${key}: expected ${expected}.`);
}

function check(key: string, value: string, re: RegExp, expected: string): string {
  if (!re.test(value)) throw invalid(key, expected);
  return value;
}

/**
 * True when EAS evaluates the config: EAS Build workers set EAS_BUILD, and
 * EAS CLI (checked in eas-cli 27.10) sets EXPO_NO_DOTENV=1 every time it
 * evaluates the app config. There, nothing silently falls back to the
 * development variant.
 */
export function isEasContext(env: Env): boolean {
  return isTruthy(read(env, "EAS_BUILD")) || isTruthy(read(env, "EXPO_NO_DOTENV"));
}

function parseVariant(env: Env): AppVariant {
  const raw = read(env, "APP_VARIANT");
  if (!raw) {
    if (isEasContext(env)) {
      throw new Error(
        "APP_VARIANT is required when EAS evaluates the app config (eas build, " +
          "eas update, eas init, ...). Export it in your shell and set it in each " +
          "EAS environment; see the Mobile > EAS section of the README.",
      );
    }
    return "development";
  }
  if (!(APP_VARIANTS as readonly string[]).includes(raw)) {
    throw invalid("APP_VARIANT", APP_VARIANTS.join(" | "));
  }
  // On EAS Build workers, a profile named after a variant must build that variant.
  const profile = read(env, "EAS_BUILD_PROFILE");
  if (
    profile &&
    (APP_VARIANTS as readonly string[]).includes(profile) &&
    profile !== raw
  ) {
    throw new Error(`APP_VARIANT does not match the EAS build profile "${profile}".`);
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
    throw invalid("API_URL", "an absolute http(s) URL");
  }
  if (url.protocol !== "https:" && url.protocol !== "http:") {
    throw invalid("API_URL", "an absolute http(s) URL");
  }
  if (url.username || url.password) {
    throw invalid("API_URL", "a URL without credentials (user:password@)");
  }
  if (/[?#]/.test(raw)) {
    throw invalid("API_URL", "a URL without a query string or fragment");
  }
  if (variant !== "development" && url.protocol !== "https:") {
    throw invalid("API_URL", `an https:// URL when APP_VARIANT=${variant}`);
  }
  // Re-serialize from the parsed URL (normalized host, no trailing slash) so
  // callers can append "/v1/...".
  return `${url.origin}${url.pathname.replace(/\/+$/, "")}`;
}

function parseAppId(
  env: Env,
  key: "ANDROID_PACKAGE" | "IOS_BUNDLE_ID",
  variant: AppVariant,
): string {
  const raw = read(env, key);
  if (variant === "production" && (!raw || PLACEHOLDER_ID_RE.test(raw))) {
    throw new Error(
      `${key} is required for production and must not use the com.example placeholder ` +
        "(Google Play rejects it). It can't change after the first store release.",
    );
  }
  const value =
    raw ?? DEFAULTS[key === "ANDROID_PACKAGE" ? "androidPackage" : "iosBundleId"];
  return key === "ANDROID_PACKAGE"
    ? check(key, value, ANDROID_PACKAGE_RE, "a Java package name like com.acme.my_app")
    : check(key, value, IOS_BUNDLE_ID_RE, "a bundle id like com.acme.my-app");
}

function claimsReservedPath(link: AppLinkPath): string | undefined {
  return RESERVED_WEB_PATHS.find((reserved) =>
    link.kind === "exact"
      ? link.path === reserved || link.path.startsWith(`${reserved}/`)
      : `${reserved}/`.startsWith(link.path) || link.path.startsWith(`${reserved}/`),
  );
}

function parseAppLinkPaths(env: Env, appDomain: string | undefined): AppLinkPath[] {
  const raw = read(env, "APP_LINK_PATHS");
  if (!raw) return [];
  if (!appDomain) throw new Error("APP_LINK_PATHS needs APP_DOMAIN.");
  const links = new Map<string, AppLinkPath>();
  for (const entry of raw.split(",").map((p) => p.trim())) {
    check(
      "APP_LINK_PATHS",
      entry,
      APP_LINK_PATH_RE,
      'comma-separated paths like "/verify-email" (exact) or "/invite/" (prefix); no wildcards',
    );
    const link: AppLinkPath = {
      kind: entry.endsWith("/") ? "prefix" : "exact",
      path: entry,
    };
    const reserved = claimsReservedPath(link);
    if (reserved) {
      throw new Error(
        `APP_LINK_PATHS must not claim ${reserved}: it must open on the web.`,
      );
    }
    links.set(entry, link);
  }
  return [...links.values()];
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
  const appDomain = appDomainRaw
    ? check("APP_DOMAIN", appDomainRaw, DOMAIN_RE, "a bare host like app.example.com")
    : undefined;
  const easProjectIdRaw = read(env, "EAS_PROJECT_ID");

  return {
    variant,
    name: `${read(env, "APP_NAME") ?? DEFAULTS.name}${nameSuffix}`,
    slug,
    owner: read(env, "EXPO_OWNER"),
    scheme: `${scheme}${suffix.replace(".", "-")}`,
    androidPackage: `${parseAppId(env, "ANDROID_PACKAGE", variant)}${suffix}`,
    iosBundleId: `${parseAppId(env, "IOS_BUNDLE_ID", variant)}${suffix}`,
    apiUrl: parseApiUrl(env, variant),
    appDomain,
    appLinkPaths: parseAppLinkPaths(env, appDomain),
    easProjectId: easProjectIdRaw
      ? check("EAS_PROJECT_ID", easProjectIdRaw, UUID_RE, "a UUID")
      : undefined,
    sentryDsn: read(env, "SENTRY_DSN"),
    googleWebClientId: parseGoogleClientId(env, "GOOGLE_WEB_CLIENT_ID"),
    googleIosClientId: parseGoogleClientId(env, "GOOGLE_IOS_CLIENT_ID"),
  };
}

const GOOGLE_CLIENT_ID_RE = /^[0-9]+-[a-z0-9]+\.apps\.googleusercontent\.com$/;

function parseGoogleClientId(env: Env, key: AppConfigEnvKey): string | undefined {
  const raw = read(env, key);
  return raw
    ? check(key, raw, GOOGLE_CLIENT_ID_RE, "like 123-abc.apps.googleusercontent.com")
    : undefined;
}

/** iOS URL scheme Google sign-in needs: the reversed iOS client id. */
export function googleIosUrlScheme(clientId: string): string {
  return `com.googleusercontent.apps.${clientId.replace(".apps.googleusercontent.com", "")}`;
}

/**
 * Per-variant runtime version. EAS Update only delivers an update to builds
 * with the same runtime version, so an update exported with the wrong variant
 * (e.g. development config published to the preview channel) can never reach
 * preview or production binaries.
 */
export function runtimeVersionFor(variant: AppVariant): string {
  return `${APP_VERSION}-${variant}`;
}

/** Values the app reads at runtime via Constants.expoConfig.extra (src/lib/env.ts). */
export interface AppExtra {
  apiUrl: string;
  appVariant: string;
  appDomain?: string;
  sentryDsn?: string;
  googleWebClientId?: string;
  googleIosClientId?: string;
  eas: { projectId?: string };
}

export default ({ config }: ConfigContext): ExpoConfig => {
  const env = parseAppEnv(process.env);
  const appLinksEnabled = env.appDomain !== undefined && env.appLinkPaths.length > 0;

  const extra: AppExtra = {
    apiUrl: env.apiUrl,
    appVariant: env.variant,
    ...(env.appDomain ? { appDomain: env.appDomain } : {}),
    ...(env.sentryDsn ? { sentryDsn: env.sentryDsn } : {}),
    ...(env.googleWebClientId ? { googleWebClientId: env.googleWebClientId } : {}),
    ...(env.googleIosClientId ? { googleIosClientId: env.googleIosClientId } : {}),
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
    runtimeVersion: runtimeVersionFor(env.variant),
    ...(env.easProjectId
      ? { updates: { url: `https://u.expo.dev/${env.easProjectId}` } }
      : {}),
    ios: {
      ...config.ios,
      bundleIdentifier: env.iosBundleId,
      supportsTablet: false,
      // iOS paths are declared server-side in apple-app-site-association.
      ...(appLinksEnabled ? { associatedDomains: [`applinks:${env.appDomain}`] } : {}),
    },
    android: {
      ...config.android,
      package: env.androidPackage,
      // Edge-to-edge is always on for Expo SDK 54+ apps (and enforced by
      // Android 15+ when targeting API 35); screens pad with safe-area insets.
      // Predictive back stays off so BackHandler listeners keep working.
      predictiveBackGestureEnabled: false,
      // No Android Auto Backup: the query cache and settings must not be
      // restored onto another device or account, and Keystore-encrypted
      // SecureStore values can't be decrypted after a restore anyway.
      allowBackup: false,
      blockedPermissions: BLOCKED_ANDROID_PERMISSIONS,
      ...(appLinksEnabled
        ? {
            intentFilters: [
              {
                action: "VIEW",
                autoVerify: true,
                data: env.appLinkPaths.map((link) =>
                  link.kind === "exact"
                    ? { scheme: "https", host: env.appDomain, path: link.path }
                    : { scheme: "https", host: env.appDomain, pathPrefix: link.path },
                ),
                category: ["BROWSABLE", "DEFAULT"],
              },
            ],
          }
        : {}),
    },
    plugins: [
      "expo-router",
      "expo-secure-store",
      "expo-notifications",
      [
        "expo-local-authentication",
        { faceIDPermission: "Allow $(PRODUCT_NAME) to unlock the app with Face ID." },
      ],
      // The plugin (no-Firebase mode) only configures the iOS URL scheme and
      // refuses to run without it; Android needs no build-time setup.
      ...(env.googleIosClientId
        ? [
            [
              "@react-native-google-signin/google-signin",
              { iosUrlScheme: googleIosUrlScheme(env.googleIosClientId) },
            ] as [string, { iosUrlScheme: string }],
          ]
        : []),
    ],
    extra,
  };
};

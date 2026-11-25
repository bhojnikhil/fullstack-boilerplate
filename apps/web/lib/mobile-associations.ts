import { warnInvalidSetting } from "@/lib/public-settings";

const packagePattern = /^[a-z][\w]*(?:\.[a-z][\w]*)+$/i;
const fingerprintPattern = /^(?:[\da-f]{2}:){31}[\da-f]{2}$/i;
const teamIdPattern = /^[A-Z0-9]{10}$/;
const bundleIdPattern = /^[a-z0-9-]+(?:\.[a-z0-9-]+)+$/i;
const pathPattern = /^\/(?:[a-z0-9_.*?~-]+\/)*[a-z0-9_.*?~-]+\/?$/i;
const publicPolicyPaths = ["/privacy", "/terms", "/account-deletion"];

function configuredValue<T>(name: string, parse: (value: string) => T | undefined) {
  const value = process.env[name]?.trim();
  if (!value) return undefined;
  const parsed = parse(value);
  if (parsed === undefined) warnInvalidSetting(name, "has an invalid value.");
  return parsed;
}

function commaSeparated(value: string) {
  return value
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
}

export function androidAppLinks() {
  const packageName = configuredValue("ANDROID_PACKAGE_NAME", (value) =>
    packagePattern.test(value) ? value : undefined,
  );
  const fingerprints = configuredValue("ANDROID_SHA256_CERT_FINGERPRINTS", (value) => {
    const entries = commaSeparated(value).map((entry) => entry.toUpperCase());
    if (entries.length && entries.every((entry) => fingerprintPattern.test(entry))) {
      return [...new Set(entries)];
    }
    return undefined;
  });
  return packageName && fingerprints ? { packageName, fingerprints } : undefined;
}

function validApplePath(path: string) {
  if (
    !pathPattern.test(path) ||
    path.split("/").some((part) => part === "." || part === "..")
  ) {
    return false;
  }

  // After validating the allowed characters, only the period needs escaping.
  const glob = path.replaceAll(".", "\\.").replace(/\*+/g, ".*").replaceAll("?", ".");
  const matcher = new RegExp(`^${glob}$`);
  return !publicPolicyPaths.some(
    (policy) => matcher.test(policy) || matcher.test(`${policy}/`),
  );
}

export function appleUniversalLinks() {
  const teamId = configuredValue("IOS_TEAM_ID", (value) => {
    const upper = value.toUpperCase();
    return teamIdPattern.test(upper) ? upper : undefined;
  });
  const bundleId = configuredValue("IOS_BUNDLE_ID", (value) =>
    bundleIdPattern.test(value) ? value : undefined,
  );
  const configuredPaths = configuredValue("IOS_APPLINK_PATHS", (value) => {
    const entries = commaSeparated(value);
    return entries.length && entries.every(validApplePath)
      ? [...new Set(entries)]
      : undefined;
  });
  const paths = process.env.IOS_APPLINK_PATHS?.trim() ? configuredPaths : ["/app/*"];

  return teamId && bundleId && paths ? { teamId, bundleId, paths } : undefined;
}

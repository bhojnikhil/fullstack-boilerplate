/**
 * Logic for `pnpm release:update <preview|production>` (release-update-cli.ts).
 *
 * One release target decides the EAS Update channel, the EAS environment and
 * the app variant, so they can't disagree. EAS overlays the hosted environment
 * variables on the invoking shell, so a missing hosted value would silently
 * fall back to whatever the shell has (e.g. APP_VARIANT=production from an
 * earlier session). The plan therefore refuses to publish unless the hosted
 * environment itself defines a matching APP_VARIANT, an API_URL valid for that
 * variant and the project id, and it removes the shell's app settings from
 * the environment `eas update` runs with.
 */
import {
  APP_CONFIG_ENV_KEYS,
  APP_VARIANTS,
  parseAppEnv,
  runtimeVersionFor,
  withoutAppConfigEnv,
} from "../app.config.ts";

export const RELEASE_TARGETS = ["preview", "production"] as const;
export type ReleaseTarget = (typeof RELEASE_TARGETS)[number];

type Env = Record<string, string | undefined>;

// App settings a hosted EAS environment may provide (not the EAS markers).
const APP_SETTING_KEYS = APP_CONFIG_ENV_KEYS.filter(
  (key) =>
    key !== "EAS_BUILD" && key !== "EAS_BUILD_PROFILE" && key !== "EXPO_NO_DOTENV",
);

export function parseReleaseTarget(arg: string | undefined): ReleaseTarget {
  if (arg && (RELEASE_TARGETS as readonly string[]).includes(arg)) {
    return arg as ReleaseTarget;
  }
  throw new Error(
    `Usage: pnpm release:update <${RELEASE_TARGETS.join("|")}> --message "<message>"`,
  );
}

/**
 * Parses the file `eas env:pull` writes: NAME=value lines. Comments (including
 * the "# NAME=***** (secret)" placeholders for secret variables) are skipped.
 */
export function parseDotenv(text: string): Record<string, string> {
  const values: Record<string, string> = {};
  for (const line of text.split(/\r?\n/)) {
    if (!line.trim() || line.trimStart().startsWith("#")) continue;
    const separator = line.indexOf("=");
    if (separator <= 0) continue;
    values[line.slice(0, separator).trim()] = line.slice(separator + 1);
  }
  return values;
}

/**
 * Environment for `eas env:pull`. EAS CLI evaluates app.config.ts first, so it
 * gets the development variant (which needs no other settings) plus the
 * project id from the shell; nothing else from the shell's app settings.
 */
export function envForPull(shellEnv: Env): Env {
  const projectId = shellEnv.EAS_PROJECT_ID?.trim();
  if (!projectId) {
    throw new Error(
      'Export EAS_PROJECT_ID (and EXPO_OWNER) first; see "EAS builds and updates" in the README.',
    );
  }
  return {
    ...withoutAppConfigEnv(shellEnv),
    APP_VARIANT: "development",
    EAS_PROJECT_ID: projectId,
    ...(shellEnv.EXPO_OWNER ? { EXPO_OWNER: shellEnv.EXPO_OWNER } : {}),
  };
}

export interface ReleasePlan {
  target: ReleaseTarget;
  runtimeVersion: string;
  apiUrl: string;
  /** Arguments for `eas`. */
  args: string[];
  /** Environment for `eas update`: the shell minus app settings, plus hosted ones. */
  env: Env;
}

export function planReleaseUpdate({
  target,
  hosted,
  shellEnv,
  message,
}: {
  target: ReleaseTarget;
  hosted: Record<string, string>;
  shellEnv: Env;
  message: string;
}): ReleasePlan {
  const where = `EAS environment "${target}"`;
  const fix = (name: string) =>
    `Set it with: pnpm exec eas env:set --environment ${target} --name ${name} --value ... --visibility plaintext`;

  const hostedVariant = hosted.APP_VARIANT?.trim();
  if (!hostedVariant)
    throw new Error(`${where} has no APP_VARIANT. ${fix("APP_VARIANT")}`);
  if (hostedVariant !== target) {
    const shown = (APP_VARIANTS as readonly string[]).includes(hostedVariant)
      ? `APP_VARIANT=${hostedVariant}`
      : "an invalid APP_VARIANT";
    throw new Error(`${where} has ${shown}; it must be ${target}.`);
  }
  if (!hosted.API_URL?.trim())
    throw new Error(`${where} has no API_URL. ${fix("API_URL")}`);
  const hostedProjectId = hosted.EAS_PROJECT_ID?.trim();
  if (!hostedProjectId) {
    throw new Error(`${where} has no EAS_PROJECT_ID. ${fix("EAS_PROJECT_ID")}`);
  }
  if (
    shellEnv.EAS_PROJECT_ID?.trim() &&
    shellEnv.EAS_PROJECT_ID.trim() !== hostedProjectId
  ) {
    throw new Error(`${where} has a different EAS_PROJECT_ID from your shell.`);
  }
  if (!message.trim())
    throw new Error('A release message is required: --message "..."');

  const appSettings: Record<string, string> = {};
  for (const key of APP_SETTING_KEYS) {
    if (hosted[key] !== undefined) appSettings[key] = hosted[key];
  }
  // Validate exactly what EAS will evaluate (throws with the config's messages).
  const appEnv = parseAppEnv({ ...appSettings, EXPO_NO_DOTENV: "1" });

  return {
    target,
    runtimeVersion: runtimeVersionFor(appEnv.variant),
    apiUrl: appEnv.apiUrl,
    args: [
      "update",
      "--channel",
      target,
      "--environment",
      target,
      "--message",
      message,
      "--non-interactive",
    ],
    env: { ...withoutAppConfigEnv(shellEnv), ...appSettings },
  };
}

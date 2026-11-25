/**
 * @jest-environment node
 */
import { execFileSync } from "node:child_process";
import path from "node:path";

import { BLOCKED_ANDROID_PERMISSIONS, withoutAppConfigEnv } from "../app.config";

/**
 * Runs Expo's config plugins in introspection mode (what `expo prebuild` would
 * write, without generating android/ or needing the Android SDK) for a
 * production config and returns the generated AndroidManifest.xml as parsed
 * by @expo/config-plugins.
 */
function introspectProductionManifest() {
  const projectRoot = path.resolve(__dirname, "..");
  const stdout = execFileSync(
    path.join(projectRoot, "node_modules/.bin/expo"),
    ["config", "--type", "introspect", "--json"],
    {
      cwd: projectRoot,
      encoding: "utf8",
      env: {
        // Explicit app settings only; nothing from the developer's shell (R2-7).
        ...withoutAppConfigEnv(process.env),
        EXPO_NO_DOTENV: "1",
        APP_VARIANT: "production",
        API_URL: "https://api.acme.dev",
        ANDROID_PACKAGE: "dev.acme.app",
        IOS_BUNDLE_ID: "dev.acme.app",
      },
    },
  );
  return JSON.parse(stdout)._internal.modResults.android.manifest.manifest;
}

type Attrs = { $: Record<string, string> };

describe("generated Android manifest (production)", () => {
  let manifest: { "uses-permission"?: Attrs[]; application: Attrs[] };

  beforeAll(() => {
    manifest = introspectProductionManifest();
  }, 120_000);

  it("disables Android Auto Backup", () => {
    expect(manifest.application[0]!.$["android:allowBackup"]).toBe("false");
  });

  it.each(BLOCKED_ANDROID_PERMISSIONS)("removes %s", (permission) => {
    const entries = (manifest["uses-permission"] ?? []).filter(
      (p) => p.$["android:name"] === permission,
    );
    expect(entries.length).toBeGreaterThan(0);
    for (const entry of entries) expect(entry.$["tools:node"]).toBe("remove");
  });

  it("keeps only the permissions the app uses", () => {
    const granted = (manifest["uses-permission"] ?? [])
      .filter((p) => p.$["tools:node"] !== "remove")
      .map((p) => p.$["android:name"]);
    expect(granted).toEqual(["android.permission.INTERNET"]);
  });

  it("keeps predictive back off", () => {
    expect(manifest.application[0]!.$["android:enableOnBackInvokedCallback"]).toBe(
      "false",
    );
  });
});

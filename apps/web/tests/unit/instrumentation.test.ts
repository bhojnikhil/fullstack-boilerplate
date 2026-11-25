import { beforeEach, expect, it, vi } from "vitest";
import { PHASE_PRODUCTION_BUILD } from "next/constants";
import { register } from "@/instrumentation";
import { GET as getAndroid } from "@/app/.well-known/assetlinks.json/route";
import { GET as getApple } from "@/app/.well-known/apple-app-site-association/route";
import { supportEmail } from "@/lib/public-settings";

beforeEach(() => {
  vi.stubEnv("NEXT_RUNTIME", "nodejs");
  vi.stubEnv("NEXT_PHASE", undefined);
  vi.stubEnv("WEB_SUPPORT_EMAIL", undefined);
  vi.stubEnv("ANDROID_PACKAGE_NAME", "com/invalid");
  vi.stubEnv("ANDROID_SHA256_CERT_FINGERPRINTS", undefined);
  vi.stubEnv("IOS_TEAM_ID", undefined);
  vi.stubEnv("IOS_BUNDLE_ID", undefined);
  vi.stubEnv("IOS_APPLINK_PATHS", "/*");
  vi.spyOn(console, "warn").mockImplementation(() => {});
});

it("warns on startup before a request and deduplicates route warnings", async () => {
  await register();

  const warnings = [
    ["[web] WEB_SUPPORT_EMAIL is missing or invalid for account deletion requests."],
    ["[web] ANDROID_PACKAGE_NAME has an invalid value."],
    ["[web] IOS_APPLINK_PATHS has an invalid value."],
  ];
  expect(vi.mocked(console.warn).mock.calls).toEqual(warnings);

  // The route bundle can get a separate instance of the settings module.
  vi.resetModules();
  const { GET } = await import("@/app/.well-known/assetlinks.json/route");
  expect(GET().status).toBe(404);
  expect(getAndroid().status).toBe(404);
  expect(getApple().status).toBe(404);
  expect(supportEmail()).toBeUndefined();
  expect(vi.mocked(console.warn).mock.calls).toEqual(warnings);
});

it("starts without warnings for valid settings or omitted optional associations", async () => {
  vi.stubEnv("WEB_SUPPORT_EMAIL", "support@example.com");
  vi.stubEnv("ANDROID_PACKAGE_NAME", "com.example.app");
  vi.stubEnv("ANDROID_SHA256_CERT_FINGERPRINTS", Array(32).fill("AB").join(":"));
  vi.stubEnv("IOS_APPLINK_PATHS", undefined);

  await register();
  expect(console.warn).not.toHaveBeenCalled();
});

it("skips runtime configuration validation while building the image", async () => {
  vi.stubEnv("NEXT_PHASE", PHASE_PRODUCTION_BUILD);
  await register();
  expect(console.warn).not.toHaveBeenCalled();
});

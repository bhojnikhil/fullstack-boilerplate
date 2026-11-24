import { beforeEach, expect, it, vi } from "vitest";
import { GET as getAndroid } from "@/app/.well-known/assetlinks.json/route";
import { GET as getApple } from "@/app/.well-known/apple-app-site-association/route";

const firstFingerprint = Array(32).fill("AB").join(":");
const secondFingerprint = Array(32).fill("CD").join(":");

beforeEach(() => {
  vi.stubEnv("ANDROID_PACKAGE_NAME", undefined);
  vi.stubEnv("ANDROID_SHA256_CERT_FINGERPRINTS", undefined);
  vi.stubEnv("IOS_TEAM_ID", undefined);
  vi.stubEnv("IOS_BUNDLE_ID", undefined);
});

it("serves all configured Android signing certificates as JSON", async () => {
  vi.stubEnv("ANDROID_PACKAGE_NAME", " com.example.my_app ");
  vi.stubEnv(
    "ANDROID_SHA256_CERT_FINGERPRINTS",
    ` ${firstFingerprint.toLowerCase()}, ${secondFingerprint} `,
  );

  const response = getAndroid();
  expect(response.status).toBe(200);
  expect(response.headers.get("content-type")).toMatch(/^application\/json\b/);
  await expect(response.json()).resolves.toEqual([
    {
      relation: ["delegate_permission/common.handle_all_urls"],
      target: {
        namespace: "android_app",
        package_name: "com.example.my_app",
        sha256_cert_fingerprints: [firstFingerprint, secondFingerprint],
      },
    },
  ]);
});

it.each([
  [undefined, firstFingerprint],
  ["com.example.my_app", undefined],
  ["com.example.my_app", `${firstFingerprint},BAD`],
  ["com/invalid", firstFingerprint],
])(
  "returns 404 for missing or invalid Android settings (%s, %s)",
  (packageName, fingerprints) => {
    vi.stubEnv("ANDROID_PACKAGE_NAME", packageName);
    vi.stubEnv("ANDROID_SHA256_CERT_FINGERPRINTS", fingerprints);
    expect(getAndroid().status).toBe(404);
  },
);

it("serves the Apple app ID and link scope as JSON", async () => {
  vi.stubEnv("IOS_TEAM_ID", " ABCDE12345 ");
  vi.stubEnv("IOS_BUNDLE_ID", " com.example.my-app ");

  const response = getApple();
  expect(response.status).toBe(200);
  expect(response.headers.get("content-type")).toMatch(/^application\/json\b/);
  await expect(response.json()).resolves.toEqual({
    applinks: {
      details: [
        { appIDs: ["ABCDE12345.com.example.my-app"], components: [{ "/": "/app/*" }] },
      ],
    },
  });
});

it.each([
  [undefined, "com.example.my-app"],
  ["ABCDE12345", undefined],
  ["short", "com.example.my-app"],
  ["ABCDE12345", "com.example.bad/id"],
])("returns 404 for missing or invalid Apple settings (%s, %s)", (teamId, bundleId) => {
  vi.stubEnv("IOS_TEAM_ID", teamId);
  vi.stubEnv("IOS_BUNDLE_ID", bundleId);
  expect(getApple().status).toBe(404);
});

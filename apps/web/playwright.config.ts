import { defineConfig, devices } from "@playwright/test";

const port = 3308;
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: "./tests/e2e",
  use: { baseURL, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `pnpm dev --hostname 127.0.0.1 --port ${port}`,
    url: baseURL,
    env: {
      NEXT_TELEMETRY_DISABLED: "1",
      WEB_SUPPORT_EMAIL: "support@example.com",
      ANDROID_PACKAGE_NAME: "com.example.boilerplate",
      ANDROID_SHA256_CERT_FINGERPRINTS: Array(32).fill("AB").join(":"),
      IOS_TEAM_ID: "ABCDE12345",
      IOS_BUNDLE_ID: "com.example.boilerplate",
    },
  },
});

import { defineConfig, devices } from "@playwright/test";

const port = 3308;
const baseURL = process.env.PLAYWRIGHT_STACK_URL || `http://127.0.0.1:${port}`;

export default defineConfig({
  forbidOnly: !!process.env.CI,
  testDir: "./tests/e2e",
  use: { baseURL, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: process.env.PLAYWRIGHT_STACK_URL
    ? undefined
    : {
        command: [
          "cp -R .next/static .next/standalone/apps/web/.next/",
          "cp -R public .next/standalone/apps/web/",
          "node .next/standalone/apps/web/server.js",
        ].join(" && "),
        url: baseURL,
        env: {
          HOSTNAME: "127.0.0.1",
          PORT: String(port),
          WEB_LEGAL_APP_NAME: "Playwright runtime app",
          WEB_LEGAL_DOMAIN: "playwright.example.com",
          NEXT_TELEMETRY_DISABLED: "1",
          WEB_SUPPORT_EMAIL: "support@example.com",
          ANDROID_PACKAGE_NAME: "com.example.boilerplate",
          ANDROID_SHA256_CERT_FINGERPRINTS: Array(32).fill("AB").join(":"),
          IOS_TEAM_ID: "ABCDE12345",
          IOS_BUNDLE_ID: "com.example.boilerplate",
          IOS_APPLINK_PATHS: "/verify-email,/reset-password,/invite/*",
        },
      },
});

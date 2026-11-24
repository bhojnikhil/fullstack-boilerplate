import { expect, test } from "@playwright/test";

test("navigates the public pages from the landing page", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle("Playwright runtime app");
  await expect(
    page.getByRole("link", { name: "Playwright runtime app" }),
  ).toHaveAttribute("href", "/");
  await expect(
    page.getByRole("heading", { level: 1, name: "Full-stack starter" }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "Create an account" })).toHaveAttribute(
    "href",
    "/auth/register",
  );

  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("main")).toBeFocused();

  const footerNav = page.getByRole("navigation", { name: "Policies and support" });
  await footerNav.getByRole("link", { name: "Privacy" }).click();
  await expect(page).toHaveURL(/\/privacy$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "Privacy policy" }),
  ).toBeVisible();
  await expect(page.getByText("Template.", { exact: true })).toBeVisible();
  await expect(page).toHaveTitle("Privacy policy | Playwright runtime app");
  await expect(
    page.getByText(/operates Playwright runtime app at playwright\.example\.com/),
  ).toBeVisible();

  await footerNav.getByRole("link", { name: "Terms" }).click();
  await expect(page).toHaveURL(/\/terms$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "Terms of service" }),
  ).toBeVisible();
  await expect(page.getByText("Template.", { exact: true })).toBeVisible();

  await footerNav.getByRole("link", { name: "Account deletion" }).click();
  await expect(page).toHaveURL(/\/account-deletion$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "Account deletion" }),
  ).toBeVisible();
  await expect(page.getByText("Template.", { exact: true })).toBeVisible();
  await expect(page.getByText(/your Playwright runtime app account/)).toBeVisible();
  await expect(page.getByRole("link", { name: "support@example.com" })).toHaveAttribute(
    "href",
    "mailto:support@example.com?subject=Account%20deletion%20request",
  );
});

test("loads the system theme and applies persisted theme tokens", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/");
  await expect(page.locator("body")).toHaveCSS("background-color", "rgb(17, 26, 23)");

  const theme = page.getByRole("combobox", { name: "Theme" });
  await expect(theme).toHaveValue("system");
  await theme.selectOption("light");
  await page.reload();
  await expect(theme).toHaveValue("light");
  await expect(page.locator("body")).toHaveCSS(
    "background-color",
    "rgb(249, 250, 248)",
  );
  expect(errors).toEqual([]);
});

test("serves both configured association URLs without a redirect", async ({
  request,
}) => {
  const android = await request.get("/.well-known/assetlinks.json", {
    maxRedirects: 0,
  });
  expect(android.status()).toBe(200);
  expect(android.headers()["content-type"]).toMatch(/^application\/json\b/);
  expect(android.headers()["cache-control"]).toBe("public, max-age=3600");
  expect(await android.json()).toMatchObject([
    { target: { package_name: "com.example.boilerplate" } },
  ]);

  const apple = await request.get("/.well-known/apple-app-site-association", {
    maxRedirects: 0,
  });
  expect(apple.status()).toBe(200);
  expect(apple.headers()["content-type"]).toMatch(/^application\/json\b/);
  expect(apple.headers()["cache-control"]).toBe("public, max-age=3600");
  expect(await apple.json()).toMatchObject({
    applinks: {
      details: [
        {
          appIDs: ["ABCDE12345.com.example.boilerplate"],
          components: [
            { "/": "/verify-email" },
            { "/": "/reset-password" },
            { "/": "/invite/*" },
          ],
        },
      ],
    },
  });
});

test("sets baseline security headers on the standalone server", async ({ request }) => {
  for (const path of ["/privacy", "/.well-known/assetlinks.json"]) {
    const response = await request.get(path);
    expect(response.status()).toBe(200);
    const headers = response.headers();
    expect(headers["x-content-type-options"]).toBe("nosniff");
    expect(headers["x-frame-options"]).toBe("DENY");
    expect(headers["content-security-policy"]).toBe("frame-ancestors 'none'");
    expect(headers["referrer-policy"]).toBe("strict-origin-when-cross-origin");
    expect(headers["x-powered-by"]).toBeUndefined();
  }
});

test("announces and focuses repeated registration validation errors", async ({
  page,
}) => {
  await page.goto("/auth/register");
  await page.getByLabel("Name", { exact: true }).fill("Test User");
  await page.getByLabel("Email", { exact: true }).fill("user@example.com");
  await page.getByLabel("Password", { exact: true }).fill("password one");
  await page.getByLabel("Confirm Password", { exact: true }).fill("password two");
  const alert = page.getByRole("alert");
  const submit = page.getByRole("button", { name: "Register" });
  await submit.click();
  const message = alert.getByText("Passwords do not match");
  await expect(message.locator("..")).toBeFocused();
  const firstMessage = await message.elementHandle();
  await submit.click();
  await expect(message.locator("..")).toBeFocused();
  expect(await firstMessage?.evaluate((element) => element.isConnected)).toBe(false);
});

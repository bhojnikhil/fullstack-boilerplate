import { expect, test } from "@playwright/test";

test("navigates the public pages from the landing page", async ({ page }) => {
  await page.goto("/");
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
  await expect(page.getByRole("link", { name: "support@example.com" })).toHaveAttribute(
    "href",
    "mailto:support@example.com?subject=Account%20deletion%20request",
  );
});

test("loads the system theme and applies persisted theme tokens", async ({ page }) => {
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
});

test("serves both configured association URLs without a redirect", async ({
  request,
}) => {
  const android = await request.get("/.well-known/assetlinks.json", {
    maxRedirects: 0,
  });
  expect(android.status()).toBe(200);
  expect(android.headers()["content-type"]).toMatch(/^application\/json\b/);
  expect(await android.json()).toMatchObject([
    { target: { package_name: "com.example.boilerplate" } },
  ]);

  const apple = await request.get("/.well-known/apple-app-site-association", {
    maxRedirects: 0,
  });
  expect(apple.status()).toBe(200);
  expect(apple.headers()["content-type"]).toMatch(/^application\/json\b/);
  expect(await apple.json()).toMatchObject({
    applinks: { details: [{ appIDs: ["ABCDE12345.com.example.boilerplate"] }] },
  });
});

import { expect, test } from "@playwright/test";

test("registers, verifies, creates a workspace and item, and signs out", async ({
  page,
  request,
}) => {
  test.skip(!process.env.PLAYWRIGHT_STACK_URL, "Requires the compose stack");
  const email = `web-${Date.now()}@example.com`;
  const password = "a secure test password 123";
  await page.goto("/auth/register");
  await page.getByLabel("Name", { exact: true }).fill("Web Test");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByLabel("Confirm Password").fill(password);
  await page.getByRole("button", { name: "Register" }).click();
  await expect(page.getByText(/Check your email/)).toBeVisible();
  const mailpit = process.env.MAILPIT_URL || "http://localhost:8025";
  let messageId = "";
  await expect
    .poll(
      async () => {
        const data = await (await request.get(`${mailpit}/api/v1/messages`)).json();
        messageId =
          data.messages?.find((message: { To: { Address: string }[] }) =>
            message.To.some((recipient) => recipient.Address === email),
          )?.ID || "";
        return messageId;
      },
      { timeout: 30000 },
    )
    .not.toBe("");
  const message = await (
    await request.get(`${mailpit}/api/v1/message/${messageId}`)
  ).json();
  const link = message.Text.match(
    /https?:\/\/[^\s]+\/auth\/verify-email#token=[^\s]+/,
  )?.[0];
  expect(link).toBeTruthy();
  await page.goto(link);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Verify email" }).click();
  await expect(page.getByText(/Your email is verified/)).toBeVisible();
  await page.goto("/auth/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Login" }).click();
  await expect(page).toHaveURL(/\/workspaces/);
  await page.getByLabel("Workspace name").fill("Test workspace");
  await page.getByRole("button", { name: "Create workspace" }).click();
  await expect(page.getByText("Workspace created.")).toBeVisible();
  await page.getByRole("link", { name: "Open items" }).click();
  await page.getByLabel("Title").fill("Test item");
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Test item" })).toBeVisible();
  await page.getByRole("button", { name: "Logout" }).click();
  await expect(page).toHaveURL(/\/(?:auth\/login)?$/);
});

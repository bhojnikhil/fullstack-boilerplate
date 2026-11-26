import { expect, test } from "@playwright/test";

test("registers, verifies, creates a workspace and item, and signs out", async ({
  page,
  request,
  browser,
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
  await page.getByLabel("New workspace name").fill("Renamed workspace");
  await page.getByRole("button", { name: "Rename workspace" }).click();
  await expect(page.getByText("Workspace renamed.")).toBeVisible();
  await page.getByRole("button", { name: "Create invitation" }).click();
  const invite = page.getByRole("link", { name: /\/invite/ });
  await expect(invite).toBeVisible();
  const inviteUrl = await invite.getAttribute("href");
  expect(inviteUrl).toBeTruthy();

  const second = await browser.newContext();
  const guest = await second.newPage();
  const guestEmail = `guest-${Date.now()}@example.com`;
  await guest.goto(`${process.env.PLAYWRIGHT_STACK_URL}/auth/register`);
  await guest.getByLabel("Name", { exact: true }).fill("Guest User");
  await guest.getByLabel("Email").fill(guestEmail);
  await guest.getByLabel("Password", { exact: true }).fill(password);
  await guest.getByLabel("Confirm Password").fill(password);
  await guest.getByRole("button", { name: "Register" }).click();
  await expect(guest.getByText(/Check your email/)).toBeVisible();
  let guestMessageId = "";
  await expect
    .poll(
      async () => {
        const data = await (await request.get(`${mailpit}/api/v1/messages`)).json();
        guestMessageId =
          data.messages?.find((message: { To: { Address: string }[] }) =>
            message.To.some((recipient) => recipient.Address === guestEmail),
          )?.ID || "";
        return guestMessageId;
      },
      { timeout: 30000 },
    )
    .not.toBe("");
  const guestMessage = await (
    await request.get(`${mailpit}/api/v1/message/${guestMessageId}`)
  ).json();
  const verifyUrl = guestMessage.Text.match(
    /https?:\/\/[^\s]+\/auth\/verify-email#token=[^\s]+/,
  )?.[0];
  expect(verifyUrl).toBeTruthy();
  await guest.goto(verifyUrl);
  await guest.getByLabel("Password").fill(password);
  await guest.getByRole("button", { name: "Verify email" }).click();
  await expect(guest.getByText(/Your email is verified/)).toBeVisible();
  await guest.goto(inviteUrl!);
  await guest.getByRole("link", { name: "Sign in", exact: true }).last().click();
  await guest.getByLabel("Email").fill(guestEmail);
  await guest.getByLabel("Password").fill(password);
  await guest.getByRole("button", { name: "Login" }).click();
  await expect(guest).toHaveURL(/\/invite/);
  await guest.getByRole("button", { name: "Accept invitation" }).click();
  await expect(guest.getByText(/Invitation accepted/)).toBeVisible();
  await page.reload();
  await expect(
    page.getByText(`Guest User (${guestEmail})`, { exact: false }),
  ).toBeVisible();
  await page.getByLabel("Password for ownership changes").fill(password);
  await page.getByLabel("Transfer ownership to").selectOption({ label: "Guest User" });
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Transfer ownership" }).click();
  await expect(page.getByText("Ownership transferred.")).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Leave Renamed workspace" }).click();
  await expect(page.getByText("Workspace left.")).toBeVisible();
  await guest.goto(`${process.env.PLAYWRIGHT_STACK_URL}/workspaces`);
  await guest.getByLabel("Password for ownership changes").fill(password);
  guest.once("dialog", (dialog) => dialog.accept());
  await guest.getByRole("button", { name: "Delete Renamed workspace" }).click();
  await expect(guest.getByText("Workspace deleted.")).toBeVisible();
  await second.close();
  await page.getByLabel("Workspace name").fill("Another workspace");
  await page.getByRole("button", { name: "Create workspace" }).click();
  await expect(page.getByText("Workspace created.")).toBeVisible();
  await page.getByRole("link", { name: "Open items" }).click();
  await page.getByLabel("Title").fill("Test item");
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Test item" })).toBeVisible();
  await page.getByRole("button", { name: "Logout" }).click();
  await expect(page).toHaveURL(/\/(?:auth\/login)?$/);
  await page.goto("/items");
  await expect(page).toHaveURL(/\/auth\/login/);
});

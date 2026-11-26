import { onlineManager } from "@tanstack/react-query";
import { router } from "expo-router";
import {
  act,
  fireEvent,
  renderRouter,
  screen,
  waitFor,
} from "expo-router/testing-library";
import path from "node:path";

import type { AppServices } from "../src/lib/app-services";
import {
  apiError,
  defaultHandlers,
  json,
  makeServices,
  tokenResponse,
  type Handlers,
} from "../test-utils/services";

const APP_DIR = path.resolve(__dirname, "../src/app");
const mockHolder: { services?: AppServices } = {};
jest.mock("@/lib/app-services", () => ({
  ...jest.requireActual("@/lib/app-services"),
  getAppServices: () => mockHolder.services,
}));

function boot(handlers: Handlers, signedIn: boolean) {
  const harness = makeServices(handlers, signedIn ? undefined : null);
  mockHolder.services = harness.services;
  return harness;
}

describe("auth flow", () => {
  it("sign-up asks to verify the email and never carries the password along", async () => {
    const harness = boot(
      {
        ...defaultHandlers(),
        "POST /v1/auth/register": () => json(202, { message: "ok" }),
      },
      false,
    );
    await renderRouter(APP_DIR, { initialUrl: "/sign-up" });
    await fireEvent.changeText(await screen.findByLabelText("Name"), "Ada");
    await fireEvent.changeText(screen.getByLabelText("Email"), "ada@example.com");
    await fireEvent.changeText(
      screen.getByLabelText("Password"),
      "correct horse battery",
    );
    await fireEvent.press(screen.getByRole("button", { name: "Create account" }));

    expect(
      await screen.findByRole("header", { name: "Check your email" }),
    ).toBeOnTheScreen();
    expect(screen.getByText(/ada@example.com/)).toBeOnTheScreen();
    expect(screen).toHavePathname("/check-email");
    expect(screen).toHaveSearchParams({ email: "ada@example.com" });
    const register = harness.requests.find((r) => r.path === "/v1/auth/register");
    expect(register?.body).toEqual({
      name: "Ada",
      email: "ada@example.com",
      password: "correct horse battery",
    });
    // The shared client sends no Idempotency-Key on auth endpoints; nothing was
    // stored as a session.
    expect(register?.headers.get("Idempotency-Key")).toBeNull();
    expect(harness.storage.current()).toBeNull();
  });

  it("explains that an unverified account can't sign in yet", async () => {
    boot(
      {
        ...defaultHandlers(),
        "POST /v1/auth/login": () => apiError(403, "email_verification_required"),
      },
      false,
    );
    await renderRouter(APP_DIR, { initialUrl: "/sign-in" });
    await fireEvent.changeText(
      await screen.findByLabelText("Email"),
      "ada@example.com",
    );
    await fireEvent.changeText(screen.getByLabelText("Password"), "pw");
    await fireEvent.press(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText(/Verify your email first/)).toBeOnTheScreen();
    expect(screen).toHavePathname("/sign-in");
  });

  it("signs in, stores the session and lands on the items", async () => {
    const harness = boot(
      {
        ...defaultHandlers(),
        "POST /v1/auth/login": () =>
          json(200, tokenResponse("sid-9", "user-9", "refresh-9")),
        "GET /v1/items": () =>
          json(200, {
            items: [
              {
                id: "i1",
                user_id: "user-9",
                title: "Milk",
                description: null,
                is_active: true,
                created_at: "2026-01-01T00:00:00Z",
                updated_at: "2026-01-01T00:00:00Z",
              },
            ],
            next_cursor: null,
          }),
      },
      false,
    );
    await renderRouter(APP_DIR, { initialUrl: "/sign-in" });
    await fireEvent.changeText(
      await screen.findByLabelText("Email"),
      "ada@example.com",
    );
    await fireEvent.changeText(screen.getByLabelText("Password"), "pw");
    await fireEvent.press(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Milk")).toBeOnTheScreen();
    expect(screen).toHavePathname("/items");
    expect(harness.storage.current()?.refreshToken).toBe("refresh-9");
    const login = harness.requests.find((r) => r.path === "/v1/auth/login");
    expect(login?.headers.get("X-Platform")).toBe("android");
    expect(login?.body).toMatchObject({ email: "ada@example.com", password: "pw" });
  });

  it("verify-email deep link sends the token and the registration password", async () => {
    const harness = boot(
      { ...defaultHandlers(), "POST /v1/auth/verify-email": () => json(204, null) },
      false,
    );
    await renderRouter(APP_DIR, { initialUrl: "/auth/verify-email?token=tok-123" });
    await fireEvent.changeText(await screen.findByLabelText("Password"), "chosen-pw");
    await fireEvent.press(screen.getByRole("button", { name: "Verify email" }));
    expect(await screen.findByText("Your email is verified.")).toBeOnTheScreen();
    expect(
      harness.requests.find((r) => r.path === "/v1/auth/verify-email")?.body,
    ).toEqual({
      token: "tok-123",
      password: "chosen-pw",
    });
  });

  it("reset-password deep link sets the new password", async () => {
    const harness = boot(
      { ...defaultHandlers(), "POST /v1/auth/password/reset": () => json(204, null) },
      false,
    );
    await renderRouter(APP_DIR, { initialUrl: "/auth/reset-password?token=rt" });
    await fireEvent.changeText(
      await screen.findByLabelText("New password"),
      "new-password-1",
    );
    await fireEvent.press(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByText(/Password changed/)).toBeOnTheScreen();
    expect(
      harness.requests.find((r) => r.path === "/v1/auth/password/reset")?.body,
    ).toEqual({
      token: "rt",
      new_password: "new-password-1",
    });
  });

  it("an invitation link asks a signed-out user to sign in first", async () => {
    boot(defaultHandlers(), false);
    await renderRouter(APP_DIR, { initialUrl: "/invite/abc" });
    expect(
      await screen.findByRole("header", { name: "Join a workspace" }),
    ).toBeOnTheScreen();
    await fireEvent.press(screen.getByRole("button", { name: "Sign in" }));
    expect(
      await screen.findByRole("header", { name: "Welcome back" }),
    ).toBeOnTheScreen();
  });
});

describe("delete account", () => {
  async function submit(handlers: Handlers) {
    const harness = boot({ ...defaultHandlers(), ...handlers }, true);
    await renderRouter(APP_DIR, { initialUrl: "/delete-account" });
    await fireEvent.changeText(
      await screen.findByLabelText("Confirm with your password"),
      "pw",
    );
    await fireEvent.press(screen.getByRole("button", { name: "Delete my account" }));
    return harness;
  }

  it("offers 'Manage workspaces' from the error code, not the message text", async () => {
    await submit({
      "POST /v1/auth/reauthenticate": () => json(204, null),
      "DELETE /v1/me": () =>
        apiError(409, "account_deletion_blocked", "Different wording", {
          reason: "sole_workspace_owner",
        }),
    });
    expect(
      await screen.findByRole("button", { name: "Manage workspaces" }),
    ).toBeOnTheScreen();
  });

  it("does not offer it for other errors, whatever the message says", async () => {
    const harness = await submit({
      "POST /v1/auth/reauthenticate": () => json(204, null),
      "DELETE /v1/me": () =>
        apiError(500, "internal_error", "Transfer or delete everything"),
    });
    await waitFor(() =>
      expect(harness.requests.some((r) => r.path === "/v1/me")).toBe(true),
    );
    expect(
      await screen.findByRole("button", { name: "Delete my account" }),
    ).toBeOnTheScreen();
    expect(screen.queryByRole("button", { name: "Manage workspaces" })).toBeNull();
  });
});

describe("items", () => {
  const server = (id: string, title: string) => ({
    id,
    user_id: "user-1",
    title,
    description: null,
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  });

  afterEach(() => {
    onlineManager.setOnline(true);
  });

  it("lists items and refetches on pull-to-refresh", async () => {
    let calls = 0;
    boot(
      {
        ...defaultHandlers(),
        "GET /v1/items": () => {
          calls += 1;
          return json(200, {
            items: [server("a", calls === 1 ? "First" : "Refreshed")],
            next_cursor: null,
          });
        },
      },
      true,
    );
    await renderRouter(APP_DIR, { initialUrl: "/items" });
    expect(await screen.findByText("First")).toBeOnTheScreen();

    // Pull-to-refresh: the list's RefreshControl calls onRefresh.
    const { refreshControl } = screen.getByTestId("items-list").props;
    await act(async () => {
      refreshControl.props.onRefresh();
    });
    expect(await screen.findByText("Refreshed")).toBeOnTheScreen();
    expect(calls).toBe(2);
  });

  it("an item created offline shows at once and syncs, once, on reconnect", async () => {
    let posts: (string | null)[] = [];
    const created = server("new-1", "Eggs");
    const harness = boot(
      {
        ...defaultHandlers(),
        "POST /v1/items": (req) => {
          posts.push(req.headers.get("Idempotency-Key"));
          return json(201, created);
        },
      },
      true,
    );
    await renderRouter(APP_DIR, { initialUrl: "/items" });
    await screen.findByText("No items yet");
    await act(async () => harness.services.workspaceId.set("ws-1"));

    await act(async () => onlineManager.setOnline(false));
    await act(async () => router.push("/item/new"));
    await fireEvent.changeText(await screen.findByLabelText("Title"), "Eggs");
    // Offline: the queue holds the write; the network is down so the send fails.
    harness.set("POST /v1/items", () => {
      throw new TypeError("Network request failed");
    });
    await fireEvent.press(screen.getByRole("button", { name: "Add item" }));

    expect(await screen.findByText("Eggs")).toBeOnTheScreen();
    expect(screen.getByText("Waiting to sync")).toBeOnTheScreen();
    expect(posts).toHaveLength(0);

    // Back online: the same request is replayed and the list refreshes.
    harness.set("POST /v1/items", (req) => {
      posts.push(req.headers.get("Idempotency-Key"));
      return json(201, created);
    });
    harness.set("GET /v1/items", () =>
      json(200, { items: [created], next_cursor: null }),
    );
    await act(async () => onlineManager.setOnline(true));

    await waitFor(() => expect(screen.queryByText("Waiting to sync")).toBeNull());
    expect(screen.getByText("Eggs")).toBeOnTheScreen();
    expect(posts).toHaveLength(1);
    expect(posts[0]).toMatch(/^[0-9a-f-]{36}$/);
    posts = [];
  });

  it("shows the update screen when the API says the app is too old", async () => {
    boot(
      {
        ...defaultHandlers(),
        "GET /v1/items": () =>
          apiError(426, "app_update_required", "Update", {
            min_supported_app_version: "9.0.0",
          }),
      },
      true,
    );
    await renderRouter(APP_DIR, { initialUrl: "/items" });
    expect(
      await screen.findByRole("header", { name: "Please update" }),
    ).toBeOnTheScreen();
    expect(screen.getByText(/9\.0\.0/)).toBeOnTheScreen();
  });
});

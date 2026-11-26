import { router } from "expo-router";
import {
  act,
  fireEvent,
  renderRouter,
  screen,
  testRouter,
} from "expo-router/testing-library";
import path from "node:path";
import { Alert, type AlertButton } from "react-native";

import type { AppServices } from "../src/lib/app-services";
import { makeServices } from "../test-utils/services";

const APP_DIR = path.resolve(__dirname, "../src/app");

// The app's service singleton is replaced per test (the mock- prefix lets the
// hoisted factory read it).
const mockHolder: { services?: AppServices } = {};
jest.mock("@/lib/app-services", () => ({
  ...jest.requireActual("@/lib/app-services"),
  getAppServices: () => mockHolder.services,
}));

function signedOut() {
  mockHolder.services = makeServices(undefined, null).services;
}
function signedIn() {
  mockHolder.services = makeServices().services;
}

describe("routing", () => {
  beforeEach(signedOut);

  it("starts at sign-in", async () => {
    await renderRouter(APP_DIR, { initialUrl: "/" });
    expect(screen).toHavePathname("/sign-in");
    expect(
      await screen.findByRole("header", { name: "Welcome back" }),
    ).toBeOnTheScreen();
    expect(screen.getByLabelText("Email")).toBeOnTheScreen();
    expect(screen.getByLabelText("Password")).toBeOnTheScreen();
  });

  it("links from sign-in to sign-up", async () => {
    await renderRouter(APP_DIR, { initialUrl: "/sign-in" });
    await fireEvent.press(await screen.findByText("Create an account"));
    expect(
      await screen.findByRole("header", { name: "Create your account" }),
    ).toBeOnTheScreen();
    expect(screen).toHavePathname("/sign-up");
  });

  it("keeps signed-out users out of the app screens", async () => {
    await renderRouter(APP_DIR, { initialUrl: "/items" });
    expect(
      await screen.findByRole("header", { name: "Welcome back" }),
    ).toBeOnTheScreen();
    expect(screen).toHavePathname("/sign-in");
  });

  it("opens the items tab for a stored session", async () => {
    signedIn();
    await renderRouter(APP_DIR, { initialUrl: "/" });
    expect(await screen.findByText("No items yet")).toBeOnTheScreen();
    expect(screen).toHavePathname("/items");
    expect(screen).toHaveSegments(["(app)", "(tabs)", "items"]);
  });

  it("switches tabs to settings", async () => {
    signedIn();
    await renderRouter(APP_DIR, { initialUrl: "/items" });
    await fireEvent.press(await screen.findByLabelText("Settings"));
    expect(
      await screen.findByRole("header", { name: "About this build" }),
    ).toBeOnTheScreen();
    expect(screen).toHavePathname("/settings");
  });

  it("serves the email-link routes whether or not anyone is signed in", async () => {
    await renderRouter(APP_DIR, { initialUrl: "/auth/verify-email?token=abc" });
    expect(
      await screen.findByRole("header", { name: "Verify your email" }),
    ).toBeOnTheScreen();
    expect(screen).toHavePathname("/auth/verify-email");
  });

  it("shows the not-found screen for unknown routes", async () => {
    await renderRouter(APP_DIR, { initialUrl: "/does-not-exist" });
    expect(await screen.findByText("This screen doesn't exist.")).toBeOnTheScreen();
  });

  describe("leaving sign-up with unsaved input (M7)", () => {
    let alert: jest.SpyInstance;
    beforeEach(() => {
      alert = jest.spyOn(Alert, "alert").mockImplementation(() => undefined);
    });
    afterEach(() => alert.mockRestore());

    function pressAlertButton(text: string) {
      const buttons = alert.mock.calls.at(-1)?.[2] as AlertButton[];
      return act(() => buttons.find((b) => b.text === text)?.onPress?.());
    }

    async function typeNameOnSignUp() {
      await renderRouter(APP_DIR, { initialUrl: "/sign-in" });
      await fireEvent.press(await screen.findByText("Create an account"));
      await fireEvent.changeText(await screen.findByLabelText("Name"), "Ada");
      await act(() => router.back());
    }

    it("asks, and Keep editing stays with the input intact", async () => {
      await typeNameOnSignUp();
      expect(alert).toHaveBeenCalledTimes(1);
      expect(alert.mock.calls[0]![0]).toBe("Discard changes?");

      await pressAlertButton("Keep editing");
      expect(screen).toHavePathname("/sign-up");
      expect(screen.getByLabelText("Name")).toHaveProp("value", "Ada");
    });

    it("Discard completes the navigation without asking again", async () => {
      await typeNameOnSignUp();
      await pressAlertButton("Discard");
      expect(
        await screen.findByRole("header", { name: "Welcome back" }),
      ).toBeOnTheScreen();
      expect(screen).toHavePathname("/sign-in");
      expect(alert).toHaveBeenCalledTimes(1);
    });

    it("leaves without asking when nothing was entered", async () => {
      await renderRouter(APP_DIR, { initialUrl: "/sign-in" });
      await fireEvent.press(await screen.findByText("Create an account"));
      await screen.findByLabelText("Name");
      await act(() => router.back());
      expect(screen).toHavePathname("/sign-in");
      expect(alert).not.toHaveBeenCalled();
    });
  });

  it("puts sign-in under a cold deep link to sign-up (M7)", async () => {
    await renderRouter(APP_DIR, { initialUrl: "/sign-up" });
    expect(
      await screen.findByRole("header", { name: "Create your account" }),
    ).toBeOnTheScreen();
    expect(testRouter.canGoBack()).toBe(true);
    await testRouter.back("/sign-in");
  });
});

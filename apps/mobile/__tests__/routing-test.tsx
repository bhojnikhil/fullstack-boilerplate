import { fireEvent, renderRouter, screen } from "expo-router/testing-library";
import path from "node:path";

const APP_DIR = path.resolve(__dirname, "../src/app");

describe("routing", () => {
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

  it("opens the tabs from the placeholder link", async () => {
    await renderRouter(APP_DIR, { initialUrl: "/sign-in" });
    await fireEvent.press(
      await screen.findByRole("button", { name: "Preview app screens" }),
    );
    expect(await screen.findByText("No items yet")).toBeOnTheScreen();
    expect(screen).toHavePathname("/items");
    expect(screen).toHaveSegments(["(app)", "items"]);
  });

  it("switches tabs to settings", async () => {
    await renderRouter(APP_DIR, { initialUrl: "/items" });
    await fireEvent.press(await screen.findByLabelText("Settings"));
    expect(
      await screen.findByRole("header", { name: "About this build" }),
    ).toBeOnTheScreen();
    expect(screen).toHavePathname("/settings");
  });

  it("shows the not-found screen for unknown routes", async () => {
    await renderRouter(APP_DIR, { initialUrl: "/does-not-exist" });
    expect(await screen.findByText("This screen doesn't exist.")).toBeOnTheScreen();
  });
});

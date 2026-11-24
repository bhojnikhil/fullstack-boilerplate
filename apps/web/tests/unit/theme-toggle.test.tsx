// @vitest-environment jsdom
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Providers } from "@/app/providers";
import { ThemeToggle } from "@/components/theme-toggle";

it("defaults to the system scheme, remembers a choice, and follows system changes", async () => {
  window.localStorage.clear();
  let prefersDark = true;
  const listeners = new Set<(event: { matches: boolean }) => void>();
  vi.stubGlobal("matchMedia", () => ({
    get matches() {
      return prefersDark;
    },
    addListener: (listener: (event: { matches: boolean }) => void) =>
      listeners.add(listener),
    removeListener: (listener: (event: { matches: boolean }) => void) =>
      listeners.delete(listener),
  }));

  const user = userEvent.setup();
  const { unmount } = render(
    <Providers>
      <ThemeToggle />
    </Providers>,
  );

  const theme = screen.getByRole("combobox", { name: "Theme" });
  expect(theme).toHaveValue("system");
  expect(document.documentElement).toHaveClass("dark");

  await user.selectOptions(theme, "light");
  expect(document.documentElement).toHaveClass("light");
  expect(window.localStorage.getItem("theme")).toBe("light");

  unmount();
  render(
    <Providers>
      <ThemeToggle />
    </Providers>,
  );
  const restoredTheme = screen.getByRole("combobox", { name: "Theme" });
  expect(restoredTheme).toHaveValue("light");

  await user.selectOptions(restoredTheme, "system");
  expect(document.documentElement).toHaveClass("dark");

  act(() => {
    prefersDark = false;
    listeners.forEach((listener) => listener({ matches: false }));
  });
  expect(document.documentElement).toHaveClass("light");
});

// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import AccountDeletionPage from "@/app/account-deletion/page";
import Home from "@/app/page";
import PrivacyPage from "@/app/privacy/page";
import TermsPage from "@/app/terms/page";

beforeEach(() => {
  vi.stubEnv("WEB_LEGAL_APP_NAME", undefined);
  vi.stubEnv("WEB_LEGAL_DOMAIN", undefined);
  vi.stubEnv("WEB_SUPPORT_EMAIL", undefined);
});

it("links directly to registration and the sample items page", () => {
  render(<Home />);
  expect(
    screen.getByRole("heading", { level: 1, name: "Full-stack starter" }),
  ).toBeVisible();
  expect(screen.getByRole("link", { name: "Create an account" })).toHaveAttribute(
    "href",
    "/auth/register",
  );
  expect(screen.getByRole("link", { name: "Open items" })).toHaveAttribute(
    "href",
    "/items",
  );
});

it.each([
  [PrivacyPage, "Privacy policy"],
  [TermsPage, "Terms of service"],
] as const)(
  "%s marks the document as a template and shows customizable details",
  (Page, title) => {
    vi.stubEnv("WEB_LEGAL_APP_NAME", "Acme App");
    vi.stubEnv("WEB_LEGAL_DOMAIN", "acme.example");
    render(<Page />);
    expect(screen.getByRole("heading", { level: 1, name: title })).toBeVisible();
    expect(
      screen.getByText(/Complete and review this page before publishing/),
    ).toBeVisible();
    expect(screen.getByText(/Acme App at acme\.example/)).toBeVisible();
  },
);

it("displays unfilled legal details and links to the deletion page", () => {
  vi.stubEnv("WEB_LEGAL_APP_NAME", "{{UNFILLED_APP_NAME}}");
  render(<PrivacyPage />);
  expect(screen.getByText(/\[App name\] at \[Site domain\]/)).toBeVisible();
  expect(screen.getByRole("link", { name: "account deletion" })).toHaveAttribute(
    "href",
    "/account-deletion",
  );
});

it("shows in-app guidance and a usable email link for requests without the app", () => {
  vi.stubEnv("WEB_SUPPORT_EMAIL", "support+deletion@example.com");
  render(<AccountDeletionPage />);
  expect(
    screen.getByRole("heading", { name: "Delete your account in the app" }),
  ).toBeVisible();
  expect(
    screen.getByRole("heading", { name: "Request deletion without the app" }),
  ).toBeVisible();
  expect(
    screen.getByRole("link", { name: "support+deletion@example.com" }),
  ).toHaveAttribute(
    "href",
    "mailto:support+deletion@example.com?subject=Account%20deletion%20request",
  );
});

it.each([undefined, "invalid@example.com?bcc=another@example.com"])(
  "shows the unconfigured request state when the mailbox is %s",
  (email) => {
    vi.stubEnv("WEB_SUPPORT_EMAIL", email);
    render(<AccountDeletionPage />);
    expect(screen.getByText(/support email has yet to be configured/)).toBeVisible();
    expect(screen.queryByRole("link")).toBeNull();
  },
);

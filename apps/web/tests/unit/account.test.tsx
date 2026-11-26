// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import AccountPage from "@/app/account/page";
const mocks = vi.hoisted(() => ({
  sessions: vi.fn(),
  changePassword: vi.fn(),
  reauthenticate: vi.fn(),
  changeEmail: vi.fn(),
  user: {
    id: "u",
    name: "User",
    email: "u@example.com",
    sign_in_methods: ["password"],
  },
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/api", () => ({ api: mocks, ApiError: class extends Error {} }));
vi.mock("@/lib/auth-store", () => ({
  useAuthStore: Object.assign(() => ({ user: mocks.user, restoreSession: vi.fn() }), {
    setState: vi.fn(),
  }),
}));
vi.mock("@/components/google-reauthenticate", () => ({
  GoogleReauthenticate: ({ onVerified }: { onVerified: () => void }) => (
    <button
      onClick={() => {
        void mocks.reauthenticate({ id_token: "google-token" }).then(onVerified);
      }}
    >
      Google verify
    </button>
  ),
}));
beforeEach(() => {
  vi.clearAllMocks();
  mocks.user.sign_in_methods = ["password"];
  mocks.sessions.mockResolvedValue({ items: [], next_cursor: null });
});
it("keeps password fields separate and clears them after submission", async () => {
  mocks.changePassword.mockResolvedValue({});
  render(<AccountPage />);
  fireEvent.change(screen.getByLabelText("Current password"), {
    target: { value: "old-password" },
  });
  fireEvent.change(screen.getByLabelText("New password"), {
    target: { value: "new-password" },
  });
  fireEvent.change(screen.getByLabelText("Password to confirm identity"), {
    target: { value: "email-password" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Change password" }));
  await waitFor(() =>
    expect(mocks.changePassword).toHaveBeenCalledWith("old-password", "new-password"),
  );
  expect(screen.getByLabelText("Current password")).toHaveValue("");
  expect(screen.getByLabelText("Password to confirm identity")).toHaveValue(
    "email-password",
  );
  expect(screen.getByLabelText("Password to delete account")).toHaveValue("");
});
it("enables email changes after Google verification for passwordless users", async () => {
  mocks.user.sign_in_methods = ["google"];
  mocks.reauthenticate.mockResolvedValue({});
  mocks.changeEmail.mockResolvedValue({});
  render(<AccountPage />);
  fireEvent.change(screen.getByLabelText("New email"), {
    target: { value: "new@example.com" },
  });
  expect(screen.getByRole("button", { name: "Request email change" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Google verify" }));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Request email change" })).toBeEnabled(),
  );
  fireEvent.click(screen.getByRole("button", { name: "Request email change" }));
  await waitFor(() =>
    expect(mocks.changeEmail).toHaveBeenCalledWith("new@example.com"),
  );
  expect(mocks.reauthenticate).toHaveBeenCalledWith({ id_token: "google-token" });
});

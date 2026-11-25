// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import ForgotPasswordPage from "@/app/auth/forgot-password/page";
import ResetPasswordPage from "@/app/auth/reset-password/page";
import ConfirmEmailPage from "@/app/auth/confirm-email/page";

const calls = vi.hoisted(() => ({
  forgotPassword: vi.fn(),
  resetPassword: vi.fn(),
  confirmEmail: vi.fn(),
}));
vi.mock("@/lib/api", () => ({ api: calls }));
beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState(null, "", "/");
});

it("gives the same generic response when requesting a reset", async () => {
  calls.forgotPassword.mockResolvedValueOnce({});
  render(<ForgotPasswordPage />);
  fireEvent.change(screen.getByLabelText("Email"), {
    target: { value: "person@example.com" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Send reset link" }));
  await screen.findByText(/If an account exists/);
  expect(calls.forgotPassword).toHaveBeenCalledWith("person@example.com");
});
it("submits the fragment token and new password and removes the token on success", async () => {
  window.history.replaceState(null, "", "/auth/reset-password#token=secret");
  calls.resetPassword.mockResolvedValueOnce(undefined);
  render(<ResetPasswordPage />);
  fireEvent.change(screen.getByLabelText("New password"), {
    target: { value: "a long password" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Reset password" }));
  await screen.findByText(/Your password has been reset/);
  expect(calls.resetPassword).toHaveBeenCalledWith("secret", "a long password");
  expect(window.location.hash).toBe("");
});
it("requires an explicit confirmation before consuming an email token", async () => {
  window.history.replaceState(null, "", "/auth/confirm-email#token=secret");
  calls.confirmEmail.mockResolvedValueOnce(undefined);
  render(<ConfirmEmailPage />);
  expect(calls.confirmEmail).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Confirm email" }));
  await waitFor(() => expect(calls.confirmEmail).toHaveBeenCalledWith("secret"));
  await screen.findByText(/Your email has been changed/);
  expect(window.location.hash).toBe("");
});

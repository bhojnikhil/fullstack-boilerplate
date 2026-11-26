// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import InvitePage from "@/app/invite/page";

const mocks = vi.hoisted(() => ({
  acceptInvitation: vi.fn(),
  setActiveWorkspace: vi.fn(),
}));
vi.mock("@/lib/api", () => ({
  api: mocks,
  setActiveWorkspace: mocks.setActiveWorkspace,
}));
vi.mock("@/lib/auth-store", () => ({
  useAuthStore: { getState: () => ({ user: { id: "u" } }) },
}));
beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  window.history.replaceState(null, "", "/invite#token=secret");
});
it("removes the token from the URL and waits for explicit acceptance", async () => {
  mocks.acceptInvitation.mockResolvedValue({ id: "w" });
  render(<InvitePage />);
  expect(window.location.hash).toBe("");
  expect(mocks.acceptInvitation).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Accept invitation" }));
  await screen.findByText(/Invitation accepted/);
  expect(mocks.acceptInvitation).toHaveBeenCalledWith("secret");
  expect(sessionStorage.length).toBe(0);
});
it("shows an error and retains the invitation after a failed acceptance", async () => {
  mocks.acceptInvitation.mockRejectedValue(new Error("invalid"));
  render(<InvitePage />);
  fireEvent.click(screen.getByRole("button", { name: "Accept invitation" }));
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("Could not accept"),
  );
  expect(sessionStorage.length).toBe(1);
});

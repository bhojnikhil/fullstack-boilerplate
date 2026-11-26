// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import WorkspacesPage from "@/app/workspaces/page";

const mocks = vi.hoisted(() => ({
  workspaces: vi.fn(),
  createWorkspace: vi.fn(),
  members: vi.fn(),
  invitations: vi.fn(),
  getActiveWorkspace: vi.fn(),
  setActiveWorkspace: vi.fn(),
  push: vi.fn(),
}));
vi.mock("next/navigation", () => {
  const router = { push: mocks.push };
  return { useRouter: () => router };
});
vi.mock("@/lib/api", () => ({
  api: mocks,
  getActiveWorkspace: mocks.getActiveWorkspace,
  setActiveWorkspace: mocks.setActiveWorkspace,
}));
vi.mock("@/lib/auth-store", () => {
  const store = { user: { id: "user" }, restoreSession: vi.fn() };
  return { useAuthStore: () => store };
});
beforeEach(() => {
  vi.clearAllMocks();
  mocks.workspaces.mockResolvedValue({ items: [], next_cursor: null });
  mocks.members.mockResolvedValue({ items: [], next_cursor: null });
  mocks.invitations.mockResolvedValue({ items: [], next_cursor: null });
  mocks.getActiveWorkspace.mockReturnValue(null);
});
it("creates and selects a workspace before opening its members", async () => {
  mocks.createWorkspace.mockResolvedValue({ id: "w1", name: "Team", role: "owner" });
  render(<WorkspacesPage />);
  await waitFor(() => expect(mocks.workspaces).toHaveBeenCalled());
  fireEvent.change(screen.getByLabelText("Workspace name"), {
    target: { value: "Team" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Create workspace" }));
  await screen.findByText("Workspace created.");
  expect(mocks.createWorkspace).toHaveBeenCalledWith("Team");
  expect(mocks.setActiveWorkspace).toHaveBeenCalledWith("w1");
  await waitFor(() => expect(mocks.members).toHaveBeenCalledWith("w1"));
});

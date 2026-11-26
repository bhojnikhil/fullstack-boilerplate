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
  const store = {
    user: { id: "user", sign_in_methods: ["password"] },
    restoreSession: vi.fn(),
  };
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
  expect(mocks.createWorkspace).toHaveBeenCalledWith("Team", "USD", "UTC");
  expect(mocks.setActiveWorkspace).toHaveBeenCalledWith("w1");
  await waitFor(() => expect(mocks.members).toHaveBeenCalledWith("w1"));
});

it("discards members from a workspace after switching", async () => {
  let resolveFirst!: (value: unknown) => void;
  mocks.workspaces.mockResolvedValue({
    items: [
      { id: "w1", name: "First", role: "member" },
      { id: "w2", name: "Second", role: "member" },
    ],
    next_cursor: null,
  });
  mocks.members.mockImplementation((id: string) =>
    id === "w1"
      ? new Promise((resolve) => {
          resolveFirst = resolve;
        })
      : Promise.resolve({
          items: [{ user_id: "b", name: "Second member", role: "member" }],
          next_cursor: null,
        }),
  );
  render(<WorkspacesPage />);
  fireEvent.click(await screen.findByRole("button", { name: "Switch to First" }));
  await waitFor(() => expect(mocks.members).toHaveBeenCalledWith("w1"));
  fireEvent.click(screen.getByRole("button", { name: "Switch to Second" }));
  await screen.findByText(/Second member/);
  resolveFirst({
    items: [{ user_id: "a", name: "Stale member", role: "member" }],
    next_cursor: null,
  });
  await waitFor(() =>
    expect(screen.queryByText(/Stale member/)).not.toBeInTheDocument(),
  );
});

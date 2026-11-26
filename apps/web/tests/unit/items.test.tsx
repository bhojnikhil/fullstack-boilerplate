// @vitest-environment jsdom
import { render, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import ItemsPage from "@/app/items/page";
const mocks = vi.hoisted(() => ({
  replace: vi.fn(),
  workspace: vi.fn(),
  setActiveWorkspace: vi.fn(),
}));
vi.mock("next/navigation", () => {
  const router = { replace: mocks.replace, push: vi.fn() };
  return { useRouter: () => router };
});
vi.mock("@/lib/api", () => ({
  api: mocks,
  getActiveWorkspace: () => "missing",
  setActiveWorkspace: mocks.setActiveWorkspace,
  ApiError: class extends Error {
    status = 404;
  },
}));
vi.mock("@/lib/auth-store", () => ({
  useAuthStore: () => ({ user: { name: "User" }, restoreSession: vi.fn() }),
}));
it("clears an unavailable workspace and redirects to workspace selection", async () => {
  const { ApiError } = await import("@/lib/api");
  mocks.workspace.mockRejectedValue(new ApiError(404, {}));
  render(<ItemsPage />);
  await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/workspaces"));
  expect(mocks.setActiveWorkspace).toHaveBeenCalledWith(null);
});

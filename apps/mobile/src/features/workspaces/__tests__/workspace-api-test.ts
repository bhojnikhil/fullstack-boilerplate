import { createAppServices } from "@/lib/app-services";
import { workspaceApi } from "../workspace-api";
import {
  apiError,
  createFakeFetch,
  json,
  makeAccessToken,
  memoryTokenStorage,
} from "../../../../test-utils/fake-api";

const headers = { "X-App-Version": "1.0.0", "X-Platform": "android" };
function setup(handlers: Parameters<typeof createFakeFetch>[0]) {
  const fake = createFakeFetch(handlers);
  const services = createAppServices({
    baseUrl: "https://api.test",
    headers,
    fetch: fake.fetch,
    storage: memoryTokenStorage({
      accessToken: makeAccessToken("sid", "user"),
      refreshToken: "refresh",
    }),
  });
  return { ...fake, services, client: workspaceApi(services.api) };
}

it("uses the real workspace and invitation payloads", async () => {
  const { client, requests, services } = setup({
    "POST /v1/workspaces": () => json(201, { id: "ws" }),
    "POST /v1/workspaces/ws/invitations": () =>
      json(201, { token: null, email: "a@example.com" }),
    "PATCH /v1/workspaces/ws/members/user2": () => new Response(null, { status: 204 }),
    "POST /v1/workspaces/ws/transfer-ownership": () =>
      new Response(null, { status: 204 }),
    "POST /v1/invitations/accept": () => json(200, { id: "ws" }),
  });
  await services.session.load();
  await client.create({ name: "Team", currency: "EUR", timezone: "Europe/Paris" });
  await client.invite("ws", "admin", "a@example.com");
  await client.changeRole("ws", "user2", "admin");
  await client.transfer("ws", "user2");
  await client.acceptInvitation("secret");
  expect(requests.map((r) => r.body)).toEqual([
    { name: "Team", currency: "EUR", timezone: "Europe/Paris" },
    { role: "admin", email: "a@example.com" },
    { role: "admin" },
    { user_id: "user2" },
    { token: "secret" },
  ]);
});

it("clears only the active workspace when its access is lost", async () => {
  const { services } = setup({
    "GET /v1/items": () => apiError(404, "workspace_not_found"),
  });
  await services.session.load();
  services.workspaceId.set("ws");
  await services.api.GET("/v1/items");
  expect(services.workspaceId.get()).toBeNull();
  expect(services.removedWorkspace.get()).toBe("ws");
});

it("uses the management endpoints and consumes their pages", async () => {
  const { client, services, requests } = setup({
    "GET /v1/workspaces": () => json(200, { items: [{ id: "ws" }], next_cursor: null }),
    "GET /v1/workspaces/ws/members": () =>
      json(200, { items: [{ user_id: "other" }], next_cursor: null }),
    "GET /v1/workspaces/ws/invitations": () =>
      json(200, { items: [{ id: "invite" }], next_cursor: null }),
    "PATCH /v1/workspaces/ws": () => json(200, { id: "ws", name: "New" }),
    "DELETE /v1/workspaces/ws/members/other": () => new Response(null, { status: 204 }),
    "DELETE /v1/workspaces/ws/invitations/invite": () =>
      new Response(null, { status: 204 }),
    "POST /v1/workspaces/ws/leave": () => new Response(null, { status: 204 }),
    "DELETE /v1/workspaces/ws": () => new Response(null, { status: 204 }),
  });
  await services.session.load();
  expect(await client.list()).toEqual([{ id: "ws" }]);
  expect(await client.members("ws")).toEqual([{ user_id: "other" }]);
  expect(await client.invitations("ws")).toEqual([{ id: "invite" }]);
  await client.rename("ws", "New");
  await client.removeMember("ws", "other");
  await client.revoke("ws", "invite");
  await client.leave("ws");
  await client.delete("ws");
  expect(requests[3]?.body).toEqual({ name: "New" });
  expect(requests.slice(4).map((r) => r.method)).toEqual([
    "DELETE",
    "DELETE",
    "POST",
    "DELETE",
  ]);
});

it("does not clear a different active workspace for a missing resource", async () => {
  const { services, client } = setup({
    "GET /v1/workspaces/other/members": () => apiError(404, "workspace_not_found"),
  });
  await services.session.load();
  services.workspaceId.set("ws");
  await expect(client.members("other")).rejects.toMatchObject({
    code: "workspace_not_found",
  });
  expect(services.workspaceId.get()).toBe("ws");
});

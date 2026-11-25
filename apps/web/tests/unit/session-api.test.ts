/** @vitest-environment jsdom */
import { afterEach, expect, it, vi } from "vitest";
import { ApiClient } from "@/lib/api";
import { createApiClient } from "@repo/api-client";

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});
function tokens(user: string, sid: string) {
  return {
    access_token: `x.${btoa(JSON.stringify({ sid }))}.x`,
    csrf_token: "csrf",
    expires_in: 900,
    user: { id: user, name: user, email: `${user}@example.com`, email_verified: true },
  };
}
function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}
it("does not retry a write when a different tab replaced the session", async () => {
  let writes = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      if (request.url.endsWith("/v1/auth/login")) return json(tokens("a", "one"));
      if (request.url.endsWith("/v1/auth/refresh")) return json(tokens("b", "two"));
      writes++;
      return json({}, 401);
    }),
  );
  const api = new ApiClient();
  await api.login("a@example.com", "password");
  await expect(api.createItem("write", "")).rejects.toThrow("different session");
  expect(writes).toBe(1);
});
it("refreshes an expired access token before revoking the same session", async () => {
  let logoutCalls = 0;
  let revoked = false;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      if (request.url.endsWith("/v1/auth/login")) return json(tokens("a", "one"));
      if (request.url.endsWith("/v1/auth/refresh"))
        return revoked ? json({}, 401) : json(tokens("a", "one"));
      if (request.url.endsWith("/v1/auth/logout")) {
        if (++logoutCalls === 1) return json({}, 401);
        revoked = true;
        return json({});
      }
      throw new Error("unexpected request");
    }),
  );
  const api = new ApiClient();
  await api.login("a@example.com", "password");
  await api.logout();
  expect(logoutCalls).toBe(2);
  expect(await api.refresh()).toBeNull();
});
it("sends configured headers and reuses an overridden idempotency key after refresh", async () => {
  const requests: Request[] = [];
  let token = "old";
  let refreshes = 0;
  const client = createApiClient({
    baseUrl: "https://example.test",
    getAccessToken: () => token,
    getSessionId: () => "session",
    getWorkspaceId: () => "workspace",
    platform: "web",
    appVersion: "1",
    requestId: () => "request",
    refresh: async () => {
      refreshes++;
      token = "new";
      return true;
    },
    fetch: async (input) => {
      requests.push(input as Request);
      return requests.length === 1 ? json({}, 401) : json({});
    },
  });
  await client.POST("/v1/items", {
    body: { title: "test" },
    headers: { "Idempotency-Key": "custom" },
  });
  expect(refreshes).toBe(1);
  expect(requests).toHaveLength(2);
  expect(Object.fromEntries(requests[0].headers)).toMatchObject({
    authorization: "Bearer old",
    "x-workspace-id": "workspace",
    "x-platform": "web",
    "x-app-version": "1",
    "x-request-id": "request",
    "idempotency-key": "custom",
  });
  expect(requests[1].headers.get("authorization")).toBe("Bearer new");
  expect(requests[1].headers.get("idempotency-key")).toBe("custom");
});

it("single-flights concurrent refreshes and preserves generated mutation keys", async () => {
  let token = "old";
  let refreshes = 0;
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const seen: Request[] = [];
  const client = createApiClient({
    baseUrl: "https://example.test",
    getAccessToken: () => token,
    getSessionId: () => "session",
    idempotencyKey: (() => {
      let n = 0;
      return () => `key-${++n}`;
    })(),
    refresh: async () => {
      refreshes++;
      await gate;
      token = "new";
      return true;
    },
    fetch: async (input) => {
      const request = input as Request;
      seen.push(request);
      return request.headers.get("authorization") === "Bearer old"
        ? json({}, 401)
        : json({});
    },
  });
  const first = client.POST("/v1/items", { body: { title: "one" } });
  const second = client.POST("/v1/items", { body: { title: "two" } });
  await vi.waitFor(() => expect(refreshes).toBe(1));
  release();
  await Promise.all([first, second]);
  expect(seen.map((r) => r.headers.get("idempotency-key")).sort()).toEqual([
    "key-1",
    "key-1",
    "key-2",
    "key-2",
  ]);
});

it("preserves credentials on transient refresh and logout failures", async () => {
  let refreshCalls = 0;
  let logoutCalls = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      if (request.url.endsWith("/v1/auth/login")) return json(tokens("a", "one"));
      if (request.url.endsWith("/v1/auth/refresh")) {
        if (++refreshCalls === 1) throw new Error("network failure");
        return json(tokens("a", "one"));
      }
      if (request.url.endsWith("/v1/auth/logout")) {
        if (++logoutCalls === 1) throw new Error("network failure");
        return json({});
      }
      throw new Error("unexpected request");
    }),
  );
  const api = new ApiClient();
  await api.login("a@example.com", "password");
  await expect(api.refresh()).rejects.toThrow("network failure");
  expect(localStorage.getItem("csrf_token")).toBe("csrf");
  expect((await api.refresh())?.user.id).toBe("a");
  await expect(api.logout()).rejects.toThrow("network failure");
  expect(localStorage.getItem("csrf_token")).toBe("csrf");
  await api.logout();
});
it("preserves another tab's CSRF value on logout", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) =>
      request.url.endsWith("/v1/auth/login") ? json(tokens("a", "one")) : json({}),
    ),
  );
  const api = new ApiClient();
  await api.login("a@example.com", "password");
  localStorage.setItem("csrf_token", "other-session-csrf");
  await api.logout();
  expect(localStorage.getItem("csrf_token")).toBe("other-session-csrf");
});
it("clears a rejected refresh credential and reports unconfirmed logout", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) =>
      request.url.endsWith("/v1/auth/login") ? json(tokens("a", "one")) : json({}, 401),
    ),
  );
  const api = new ApiClient();
  await api.login("a@example.com", "password");
  expect(await api.refresh()).toBeNull();
  expect(localStorage.getItem("csrf_token")).toBeNull();
  await expect(api.logout()).rejects.toThrow("Could not confirm sign out");
});

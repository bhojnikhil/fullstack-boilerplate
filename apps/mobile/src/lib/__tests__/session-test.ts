import { createAppServices } from "../app-services";
import {
  apiError,
  createFakeFetch,
  json,
  makeAccessToken,
  memoryTokenStorage,
  tokenResponse,
} from "../../../test-utils/fake-api";

const HEADERS = { "X-App-Version": "1.0.0", "X-Platform": "android" };

function setup(
  handlers: Parameters<typeof createFakeFetch>[0],
  initial = {
    accessToken: makeAccessToken("sid-A", "user-A"),
    refreshToken: "refresh-A",
  },
) {
  const fake = createFakeFetch(handlers);
  const storage = memoryTokenStorage(initial);
  const services = createAppServices({
    baseUrl: "https://api.test",
    headers: HEADERS,
    storage,
    fetch: fake.fetch,
  });
  return { ...fake, storage, services };
}

describe("token refresh", () => {
  it("refreshes once for concurrent 401s and retries each request with the new token", async () => {
    const newToken = makeAccessToken("sid-A", "user-A", "rotated");
    let refreshes = 0;
    const { services, requests, storage } = setup({
      "GET /v1/items": (req) =>
        req.headers.get("Authorization") === `Bearer ${newToken}`
          ? json(200, { items: [], next_cursor: null })
          : apiError(401, "invalid_token"),
      "POST /v1/auth/refresh": async () => {
        refreshes += 1;
        await new Promise((resolve) => setTimeout(resolve, 10));
        return json(200, {
          ...tokenResponse("sid-A", "user-A", "refresh-A2"),
          access_token: newToken,
        });
      },
    });
    await services.session.load();

    const [a, b, c] = await Promise.all([
      services.api.GET("/v1/items"),
      services.api.GET("/v1/items"),
      services.api.GET("/v1/items"),
    ]);

    expect([a.response.status, b.response.status, c.response.status]).toEqual([
      200, 200, 200,
    ]);
    expect(refreshes).toBe(1);
    expect(requests.filter((r) => r.path === "/v1/auth/refresh")[0]?.body).toEqual({
      refresh_token: "refresh-A",
    });
    // The rotated pair replaced the old one, in one record.
    expect(storage.current()).toEqual({
      accessToken: newToken,
      refreshToken: "refresh-A2",
    });
  });

  it("does not replay a pending request when the session changed during the refresh", async () => {
    let releaseRefresh: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      releaseRefresh = resolve;
    });
    const { services, requests, storage } = setup({
      "GET /v1/items": () => apiError(401, "invalid_token"),
      "POST /v1/auth/refresh": async () => {
        await gate;
        return json(200, tokenResponse("sid-A", "user-A", "refresh-A2"));
      },
    });
    await services.session.load();

    const pending = services.api.GET("/v1/items");
    await new Promise((resolve) => setTimeout(resolve, 5)); // 401 seen, refresh in flight
    // The user signs out and into another account while the refresh is out.
    await services.session.signIn({
      accessToken: makeAccessToken("sid-B", "user-B"),
      refreshToken: "refresh-B",
    });
    releaseRefresh();

    await expect(pending).rejects.toMatchObject({ name: "SessionChangedError" });
    // Only the original (401) request was ever sent: no replay as account B.
    expect(requests.filter((r) => r.path === "/v1/items")).toHaveLength(1);
    // Account B's session is untouched by account A's late refresh response.
    expect(services.session.getState()).toMatchObject({
      sessionId: "sid-B",
      refreshToken: "refresh-B",
    });
    expect(storage.current()?.refreshToken).toBe("refresh-B");
  });

  it("never adopts a refresh that lands on a different session", async () => {
    const { services, storage } = setup({
      "GET /v1/items": () => apiError(401, "invalid_token"),
      "POST /v1/auth/refresh": () =>
        json(200, tokenResponse("sid-OTHER", "user-OTHER")),
    });
    await services.session.load();

    const result = await services.api.GET("/v1/items");

    expect(result.response.status).toBe(401);
    expect(services.session.getState().status).toBe("signedOut");
    expect(storage.current()).toBeNull();
  });

  it("signs out when the refresh token is rejected", async () => {
    const { services, storage } = setup({
      "GET /v1/items": () => apiError(401, "invalid_token"),
      "POST /v1/auth/refresh": () => apiError(401, "invalid_refresh_token"),
    });
    await services.session.load();
    await services.api.GET("/v1/items");
    expect(services.session.getState().status).toBe("signedOut");
    expect(storage.current()).toBeNull();
  });

  it("keeps the session when the refresh fails for a transient reason", async () => {
    const { services, storage } = setup({
      "GET /v1/items": () => apiError(401, "invalid_token"),
      "POST /v1/auth/refresh": () => apiError(503, "unavailable"),
    });
    await services.session.load();
    await expect(services.api.GET("/v1/items")).rejects.toMatchObject({ status: 503 });
    expect(services.session.getState().status).toBe("signedIn");
    expect(storage.current()?.refreshToken).toBe("refresh-A");
  });
});

describe("request headers", () => {
  it("sends version, platform, workspace, bearer and a stable idempotency key on writes", async () => {
    const { services, requests } = setup({
      "POST /v1/items": () => json(201, {}),
      "GET /v1/items": () => json(200, { items: [], next_cursor: null }),
    });
    await services.session.load();
    services.workspaceId.set("ws-1");

    await services.api.GET("/v1/items");
    await services.api.POST("/v1/items", { body: { title: "x" } });
    await services.api.POST("/v1/items", {
      body: { title: "y" },
      headers: { "Idempotency-Key": "fixed-key" },
    });

    const [get, post, keyed] = requests;
    for (const request of [get, post, keyed]) {
      expect(request?.headers.get("X-App-Version")).toBe("1.0.0");
      expect(request?.headers.get("X-Platform")).toBe("android");
      expect(request?.headers.get("X-Workspace-Id")).toBe("ws-1");
      expect(request?.headers.get("Authorization")).toMatch(/^Bearer /);
    }
    expect(get?.headers.get("Idempotency-Key")).toBeNull();
    expect(post?.headers.get("Idempotency-Key")).toMatch(/^[0-9a-f-]{36}$/);
    expect(keyed?.headers.get("Idempotency-Key")).toBe("fixed-key");
  });

  it("flags the app as outdated on 426", async () => {
    const { services } = setup({
      "GET /v1/items": () =>
        apiError(426, "app_update_required", "Update", {
          min_supported_app_version: "2.0.0",
        }),
    });
    await services.session.load();
    await services.api.GET("/v1/items");
    expect(services.updateRequired.get()).toEqual({ minVersion: "2.0.0" });
  });
});

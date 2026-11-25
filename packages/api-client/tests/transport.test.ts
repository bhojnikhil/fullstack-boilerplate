import { afterEach, describe, expect, it, vi } from "vitest";
import { createApiClient, SessionChangedError } from "../src/index";

const unauthorized = () => new Response(null, { status: 401 });
const ok = () =>
  new Response(JSON.stringify({}), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
const mutation = (
  client: ReturnType<typeof createApiClient>,
  headers?: Record<string, string>,
) =>
  client.POST("/v1/items", { body: { title: "test", description: "test" }, headers });

afterEach(() => vi.unstubAllGlobals());
describe("transport", () => {
  it("does not replay a write when the session changes during refresh", async () => {
    let session = "a";
    const send = vi.fn(async () => unauthorized());
    const changed = vi.fn();
    const client = createApiClient({
      baseUrl: "https://example.test",
      fetch: send,
      getSessionId: () => session,
      refresh: async () => {
        session = "b";
        return true;
      },
      onSessionChanged: changed,
    });
    await expect(mutation(client)).rejects.toBeInstanceOf(SessionChangedError);
    expect(send).toHaveBeenCalledTimes(1);
    expect(changed).toHaveBeenCalledOnce();
  });
  it("returns the 401 and reports failed refresh without replay", async () => {
    const failed = vi.fn();
    const send = vi.fn(async () => unauthorized());
    const client = createApiClient({
      baseUrl: "https://example.test",
      fetch: send,
      refresh: async () => false,
      onRefreshFailed: failed,
    });
    expect((await mutation(client)).response.status).toBe(401);
    expect(send).toHaveBeenCalledOnce();
    expect(failed).toHaveBeenCalledOnce();
  });
  it("exempts auth endpoints under a URL prefix and sends no idempotency key", async () => {
    const refresh = vi.fn(async () => true);
    const send = vi.fn(async () => unauthorized());
    const client = createApiClient({
      baseUrl: "https://example.test/api",
      fetch: send,
      refresh,
    });
    await client.POST("/v1/auth/refresh");
    expect(refresh).not.toHaveBeenCalled();
    expect((send.mock.calls[0][0] as Request).headers.has("Idempotency-Key")).toBe(
      false,
    );
  });
  it("refreshes with a null session and reuses an overridable key on retry", async () => {
    let token: string | null = null;
    const requests: Request[] = [];
    const refresh = vi.fn(async (expected: string | null) => {
      expect(expected).toBeNull();
      token = "new";
      return true;
    });
    const client = createApiClient({
      baseUrl: "https://example.test",
      getAccessToken: () => token,
      getSessionId: () => (token ? "new-session" : null),
      refresh,
      fetch: async (input) => {
        requests.push(input as Request);
        return requests.length === 1 ? unauthorized() : ok();
      },
    });
    await mutation(client, { "Idempotency-Key": "chosen" });
    expect(requests.map((r) => r.headers.get("Idempotency-Key"))).toEqual([
      "chosen",
      "chosen",
    ]);
    expect(requests[1].headers.get("Authorization")).toBe("Bearer new");
  });
  it("sets keys for mutations but not GET and preserves caller authorization", async () => {
    const requests: Request[] = [];
    const refresh = vi.fn(async () => true);
    const client = createApiClient({
      baseUrl: "https://example.test",
      idempotencyKey: () => "generated",
      getAccessToken: () => "default",
      refresh,
      fetch: async (input) => {
        requests.push(input as Request);
        return unauthorized();
      },
    });
    await client.GET("/v1/me", { headers: { Authorization: "Bearer custom" } });
    await mutation(client, { Authorization: "Bearer custom" });
    expect(requests).toHaveLength(2);
    expect(refresh).not.toHaveBeenCalled();
    expect(requests[0].headers.has("Idempotency-Key")).toBe(false);
    expect(requests[1].headers.get("Idempotency-Key")).toBe("generated");
    expect(requests[1].headers.get("Authorization")).toBe("Bearer custom");
  });
  it("joins an in-flight refresh", async () => {
    let resolve!: (value: boolean) => void;
    const refresh = vi.fn(
      () =>
        new Promise<boolean>((r) => {
          resolve = r;
        }),
    );
    let sends = 0;
    const client = createApiClient({
      baseUrl: "https://example.test",
      refresh,
      fetch: async () => (++sends <= 2 ? unauthorized() : ok()),
    });
    const first = client.GET("/v1/me");
    const second = client.GET("/v1/me");
    await vi.waitFor(() => expect(refresh).toHaveBeenCalledOnce());
    resolve(true);
    await Promise.all([first, second]);
    expect(sends).toBe(4);
    expect(refresh).toHaveBeenCalledOnce();
  });
  it("uses getRandomValues when randomUUID is unavailable", async () => {
    const getRandomValues = vi.fn((bytes: Uint8Array) => {
      bytes.fill(1);
      return bytes;
    });
    vi.stubGlobal("crypto", { getRandomValues });
    const requests: Request[] = [];
    const client = createApiClient({
      baseUrl: "https://example.test",
      fetch: async (input) => {
        requests.push(input as Request);
        return ok();
      },
    });
    await mutation(client);
    expect(requests[0].headers.get("X-Request-Id")).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    );
    expect(getRandomValues).toHaveBeenCalledTimes(2);
  });
});

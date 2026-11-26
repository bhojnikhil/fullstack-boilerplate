import type { TokenStorage, AuthTokens } from "../src/lib/token-storage";

export interface RecordedRequest {
  method: string;
  path: string;
  headers: Headers;
  body: unknown;
}

type Handler = (request: RecordedRequest) => Response | Promise<Response>;

export function json(status: number, body: unknown): Response {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export function apiError(
  status: number,
  code: string,
  message = code,
  details = {},
): Response {
  return json(status, { error: { code, message, details } });
}

/** A fetch that answers from a `"METHOD /path"` table and records every request. */
export function createFakeFetch(handlers: Record<string, Handler>) {
  const requests: RecordedRequest[] = [];
  const table = new Map(Object.entries(handlers));
  const fetch = async (
    input: RequestInfo | URL,
    init?: RequestInit,
  ): Promise<Response> => {
    const request = new Request(input, init);
    const text = await request.clone().text();
    const recorded: RecordedRequest = {
      method: request.method,
      path: new URL(request.url).pathname,
      headers: request.headers,
      body: text ? (JSON.parse(text) as unknown) : undefined,
    };
    requests.push(recorded);
    const handler = table.get(`${recorded.method} ${recorded.path}`);
    if (!handler)
      return apiError(
        404,
        "not_found",
        `no handler for ${recorded.method} ${recorded.path}`,
      );
    return handler(recorded);
  };
  return {
    fetch: fetch as typeof globalThis.fetch,
    requests,
    set: (key: string, handler: Handler) => table.set(key, handler),
  };
}

/** Unsigned JWT-shaped token carrying the claims the app reads. */
export function makeAccessToken(sid: string, sub = "user-1", nonce = ""): string {
  const encode = (value: object) =>
    Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none", typ: "at+jwt" })}.${encode({ sid, sub, nonce })}.sig`;
}

export function tokenResponse(
  sid: string,
  sub = "user-1",
  refresh = `refresh-${sid}-next`,
) {
  return {
    access_token: makeAccessToken(sid, sub),
    refresh_token: refresh,
    csrf_token: null,
    expires_in: 900,
    token_type: "bearer",
    user: {
      id: sub,
      email: "a@example.com",
      email_verified: true,
      name: "A",
      avatar_url: null,
      sign_in_methods: ["password"],
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
  };
}

export function memoryTokenStorage(initial?: AuthTokens | null): TokenStorage & {
  current(): AuthTokens | null;
} {
  let tokens = initial ?? null;
  return {
    getTokens: async () => tokens,
    setTokens: async (next) => {
      tokens = next;
    },
    clearTokens: async () => {
      tokens = null;
    },
    current: () => tokens,
  };
}

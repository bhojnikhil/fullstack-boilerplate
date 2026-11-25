import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

export type { components, paths } from "./schema";
export type ErrorEnvelope = components["schemas"]["ErrorEnvelope"];

export class SessionChangedError extends Error {
  constructor() {
    super("Signed in as a different session in another tab; the request was not sent.");
    this.name = "SessionChangedError";
  }
}

export interface ClientOptions {
  baseUrl: string;
  fetch?: typeof globalThis.fetch;
  credentials?: RequestCredentials;
  getAccessToken?: () => string | null;
  getSessionId?: () => string | null;
  getWorkspaceId?: () => string | null;
  appVersion?: string;
  platform?: string;
  requestId?: () => string;
  idempotencyKey?: () => string;
  refresh?: (expectedSession: string | null) => Promise<boolean>;
  onSessionChanged?: () => void;
  onRefreshFailed?: () => void;
}

/** Shared transport. A retry retains its original body and idempotency key. */
export function createApiClient(options: ClientOptions) {
  let refreshing: Promise<boolean> | null = null;
  const transport: typeof globalThis.fetch = async (input, init) => {
    const request = new Request(input, init);
    const originalSession = options.getSessionId?.() ?? null;
    const headers = new Headers(request.headers);
    const set = (name: string, value: string | null | undefined) => {
      if (value && !headers.has(name)) headers.set(name, value);
    };
    set(
      "Authorization",
      options.getAccessToken?.() ? `Bearer ${options.getAccessToken!()}` : null,
    );
    set("X-Workspace-Id", options.getWorkspaceId?.());
    set("X-App-Version", options.appVersion);
    set("X-Platform", options.platform);
    set("X-Request-Id", options.requestId?.() ?? globalThis.crypto.randomUUID());
    if (!["GET", "HEAD", "OPTIONS"].includes(request.method))
      set(
        "Idempotency-Key",
        options.idempotencyKey?.() ?? globalThis.crypto.randomUUID(),
      );
    const prepared = new Request(request, {
      headers,
      credentials: options.credentials,
    });
    const send = options.fetch ?? globalThis.fetch;
    const response = await send(prepared.clone());
    if (
      response.status !== 401 ||
      !options.refresh ||
      new URL(request.url).pathname.startsWith("/v1/auth/")
    )
      return response;
    if (!originalSession) return response;
    refreshing ??= options.refresh(originalSession).finally(() => {
      refreshing = null;
    });
    const refreshed = await refreshing;
    if (!refreshed) {
      options.onRefreshFailed?.();
      return response;
    }
    if (originalSession !== (options.getSessionId?.() ?? null)) {
      options.onSessionChanged?.();
      throw new SessionChangedError();
    }
    const retryHeaders = new Headers(prepared.headers);
    const token = options.getAccessToken?.();
    if (token) retryHeaders.set("Authorization", `Bearer ${token}`);
    else retryHeaders.delete("Authorization");
    return send(new Request(prepared, { headers: retryHeaders }));
  };
  return createClient<paths>({ baseUrl: options.baseUrl, fetch: transport });
}

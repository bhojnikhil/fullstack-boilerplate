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

function secureUuid(): string {
  const crypto = globalThis.crypto;
  if (crypto?.randomUUID) return crypto.randomUUID();
  if (!crypto?.getRandomValues)
    throw new Error(
      "A secure random number generator is required to create request IDs and idempotency keys",
    );
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
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
    const callerAuthorization = headers.has("Authorization");
    const accessToken = options.getAccessToken?.();
    set("Authorization", accessToken ? `Bearer ${accessToken}` : null);
    const path = new URL(request.url).pathname;
    const authPath = /(?:^|\/)v1\/auth(?:\/|$)/.test(path);
    // Credential endpoints either establish, rotate, or explicitly revoke a session.
    // Authenticated session-management calls still need the normal refresh path.
    const credentialPath =
      /(?:^|\/)v1\/auth\/(?:login|register|refresh|google|verify-email(?:\/resend)?|password\/(?:forgot|reset)|email\/confirm|logout)\/?$/.test(
        path,
      );
    set("X-Workspace-Id", options.getWorkspaceId?.());
    set("X-App-Version", options.appVersion);
    set("X-Platform", options.platform);
    if (!headers.has("X-Request-Id"))
      set("X-Request-Id", options.requestId?.() ?? secureUuid());
    if (
      !authPath &&
      !headers.has("Idempotency-Key") &&
      !["GET", "HEAD", "OPTIONS"].includes(request.method)
    )
      set("Idempotency-Key", options.idempotencyKey?.() ?? secureUuid());
    const prepared = new Request(request, {
      headers,
      credentials: options.credentials,
    });
    const send = options.fetch ?? globalThis.fetch;
    const response = await send(prepared.clone());
    if (
      response.status !== 401 ||
      !options.refresh ||
      callerAuthorization ||
      credentialPath
    )
      return response;
    refreshing ??= options.refresh(originalSession).finally(() => {
      refreshing = null;
    });
    const refreshed = await refreshing;
    if (!refreshed) {
      options.onRefreshFailed?.();
      return response;
    }
    if (
      originalSession !== null &&
      originalSession !== (options.getSessionId?.() ?? null)
    ) {
      await response.body?.cancel();
      options.onSessionChanged?.();
      throw new SessionChangedError();
    }
    await response.body?.cancel();
    const retryHeaders = new Headers(prepared.headers);
    const token = options.getAccessToken?.();
    if (token) retryHeaders.set("Authorization", `Bearer ${token}`);
    else retryHeaders.delete("Authorization");
    return send(new Request(prepared, { headers: retryHeaders }));
  };
  return createClient<paths>({ baseUrl: options.baseUrl, fetch: transport });
}

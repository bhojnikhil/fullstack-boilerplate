import { ApiError, readApiError } from "./api-error";
import { decodeAccessClaims } from "./jwt";
import type { AuthTokens, TokenStorage } from "./token-storage";

export type SessionStatus = "loading" | "signedOut" | "signedIn";

export interface SessionState {
  status: SessionStatus;
  /** Account id (JWT `sub`); scopes the query cache, queue and workspace choice. */
  accountId: string | null;
  /** Session id (JWT `sid`); every request and its refresh stay bound to it. */
  sessionId: string | null;
  accessToken: string | null;
  refreshToken: string | null;
}

const LOADING: SessionState = {
  status: "loading",
  accountId: null,
  sessionId: null,
  accessToken: null,
  refreshToken: null,
};
const SIGNED_OUT: SessionState = { ...LOADING, status: "signedOut" };

export interface SessionStore {
  getState(): SessionState;
  subscribe(listener: () => void): () => void;
  /** Reads the stored tokens once at startup. */
  load(): Promise<void>;
  /** Adopts the tokens of a fresh sign-in (replacing any previous session). */
  signIn(tokens: AuthTokens): Promise<void>;
  /** Forgets the session locally (the server side is the caller's business). */
  signOut(): Promise<void>;
  /**
   * Rotates the tokens of `expectedSession` (the session a request was sent
   * as). Single-flight. Resolves:
   * - true: the request may be retried. If the session has since changed, the
   *   api-client sees that and refuses to replay it.
   * - false: the refresh token was rejected; this session was signed out.
   * Rejects on transient failures (network, 5xx) WITHOUT signing out.
   */
  refresh(expectedSession: string | null): Promise<boolean>;
}

export type RefreshRequest = (refreshToken: string) => Promise<{
  access_token: string;
  refresh_token: string | null;
}>;

export function createSessionStore(deps: {
  storage: TokenStorage;
  requestRefresh: RefreshRequest;
}): SessionStore {
  const { storage, requestRefresh } = deps;
  let state: SessionState = LOADING;
  /** Bumped whenever the identity changes; a refresh from an older epoch is void. */
  let epoch = 0;
  let inflight: { sessionId: string; promise: Promise<boolean> } | null = null;
  // Storage writes and the state change they belong to happen as one step.
  let chain: Promise<unknown> = Promise.resolve();
  const listeners = new Set<() => void>();

  const serial = <T>(task: () => Promise<T>): Promise<T> => {
    const run = chain.then(task, task);
    chain = run.catch(() => undefined);
    return run;
  };
  const set = (next: SessionState) => {
    state = next;
    listeners.forEach((listener) => listener());
  };
  const fromTokens = (tokens: AuthTokens): SessionState | null => {
    const claims = decodeAccessClaims(tokens.accessToken);
    if (!claims) return null;
    return {
      status: "signedIn",
      accountId: claims.sub,
      sessionId: claims.sid,
      accessToken: tokens.accessToken,
      refreshToken: tokens.refreshToken,
    };
  };

  async function doRefresh(sessionId: string, refreshToken: string): Promise<boolean> {
    const startedEpoch = epoch;
    let response;
    try {
      response = await requestRefresh(refreshToken);
    } catch (error) {
      if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
        await serial(async () => {
          if (epoch !== startedEpoch) return; // someone else is signed in now
          epoch += 1;
          await storage.clearTokens();
          set(SIGNED_OUT);
        });
        return false;
      }
      throw error; // transient: keep the session
    }
    return serial(async () => {
      // Signed out, or signed in as someone else, while the request was out:
      // drop the new tokens; the caller sees the changed session.
      if (epoch !== startedEpoch) return true;
      const next = response.refresh_token
        ? fromTokens({
            accessToken: response.access_token,
            refreshToken: response.refresh_token,
          })
        : null;
      if (!next || next.sessionId !== sessionId) {
        // A refresh that lands on another session/account is never adopted.
        epoch += 1;
        await storage.clearTokens();
        set(SIGNED_OUT);
        return false;
      }
      await storage.setTokens({
        accessToken: next.accessToken!,
        refreshToken: next.refreshToken!,
      });
      set(next);
      return true;
    });
  }

  return {
    getState: () => state,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    load: () =>
      serial(async () => {
        const tokens = await storage.getTokens();
        const next = tokens ? fromTokens(tokens) : null;
        epoch += 1;
        set(next ?? SIGNED_OUT);
      }),
    signIn: (tokens) =>
      serial(async () => {
        const next = fromTokens(tokens);
        if (!next) throw new Error("The server returned an unreadable access token.");
        await storage.setTokens(tokens);
        epoch += 1;
        set(next);
      }),
    signOut: () =>
      serial(async () => {
        epoch += 1;
        await storage.clearTokens();
        set(SIGNED_OUT);
      }),
    refresh(expectedSession) {
      const current = state;
      if (
        !expectedSession ||
        current.sessionId !== expectedSession ||
        !current.refreshToken
      ) {
        // The session the request was sent as is gone: nothing to refresh.
        // Returning true makes the api-client notice the mismatch and refuse
        // to replay the request.
        return Promise.resolve(true);
      }
      if (inflight?.sessionId === expectedSession) return inflight.promise;
      const promise = doRefresh(expectedSession, current.refreshToken).finally(() => {
        if (inflight?.promise === promise) inflight = null;
      });
      inflight = { sessionId: expectedSession, promise };
      return promise;
    },
  };
}

/** POST /v1/auth/refresh with the refresh token in the body (mobile transport). */
export function createRefreshRequest(options: {
  baseUrl: string;
  headers: Record<string, string>;
  fetch?: typeof globalThis.fetch;
}): RefreshRequest {
  return async (refreshToken) => {
    const send = options.fetch ?? globalThis.fetch;
    const response = await send(`${options.baseUrl}/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...options.headers },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!response.ok) throw await readApiError(response);
    return (await response.json()) as Awaited<ReturnType<RefreshRequest>>;
  };
}

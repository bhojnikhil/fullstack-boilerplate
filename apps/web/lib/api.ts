import {
  createApiClient,
  SessionChangedError,
  type components,
} from "@repo/api-client";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const CSRF_STORAGE_KEY = "csrf_token";
export type Item = components["schemas"]["ItemResponse"];
export type User = components["schemas"]["UserResponse"];
type TokenResponse = components["schemas"]["TokenResponse"];

let accessToken: string | null = null;
let identity: string | null = null;
let sessionCsrf: string | null = null;
let refreshing: Promise<TokenResponse | null> | null = null;
function tokenIdentity(tokens: TokenResponse): string {
  try {
    const payload = JSON.parse(
      atob(tokens.access_token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")),
    );
    return `${tokens.user.id}:${payload.sid}`;
  } catch {
    return `${tokens.user.id}:invalid`;
  }
}
function storage(): Storage | null {
  try {
    return typeof window !== "undefined" ? window.localStorage : null;
  } catch {
    return null;
  }
}
function startSession(tokens: TokenResponse) {
  accessToken = tokens.access_token;
  identity = tokenIdentity(tokens);
  sessionCsrf = tokens.csrf_token;
  if (tokens.csrf_token) storage()?.setItem(CSRF_STORAGE_KEY, tokens.csrf_token);
}
function endSession() {
  accessToken = null;
  identity = null;
  if (sessionCsrf && storage()?.getItem(CSRF_STORAGE_KEY) === sessionCsrf)
    storage()?.removeItem(CSRF_STORAGE_KEY);
  sessionCsrf = null;
}
function changedSession() {
  accessToken = null;
  identity = null;
  sessionCsrf = null;
  if (typeof window !== "undefined")
    window.dispatchEvent(new Event("auth-session-changed"));
}
function oneAtATime<T>(task: () => Promise<T>): Promise<T> {
  if (typeof navigator !== "undefined" && "locks" in navigator)
    return navigator.locks.request("auth-refresh", task);
  return task();
}
export class ApiError extends Error {
  constructor(
    public status: number,
    public body: unknown,
  ) {
    super(`API request failed (${status})`);
  }
}
function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (!result.response.ok) throw new ApiError(result.response.status, result.error);
  return result.data as T;
}
export class ApiClient {
  private client = createApiClient({
    baseUrl: API_URL,
    credentials: "include",
    platform: "web",
    getAccessToken: () => accessToken,
    getSessionId: () => identity,
    refresh: async (expected) => !!(await this.refresh(expected)),
    onSessionChanged: changedSession,
    onRefreshFailed: () => {
      if (typeof window !== "undefined") window.location.href = "/auth/login";
    },
  });
  private authClient = createApiClient({
    baseUrl: API_URL,
    credentials: "include",
    platform: "web",
  });
  refresh(expectedIdentity?: string | null): Promise<TokenResponse | null> {
    refreshing ??= oneAtATime(async () => {
      const csrf = storage()?.getItem(CSRF_STORAGE_KEY);
      if (!csrf) return null;
      try {
        return unwrap(
          await this.authClient.POST("/v1/auth/refresh", {
            headers: { "X-CSRF-Token": csrf },
          }),
        );
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          if (storage()?.getItem(CSRF_STORAGE_KEY) === csrf)
            storage()?.removeItem(CSRF_STORAGE_KEY);
          accessToken = null;
          identity = null;
          sessionCsrf = null;
          return null;
        }
        throw error;
      }
    }).finally(() => {
      refreshing = null;
    });
    return refreshing.then((data) => {
      if (
        data &&
        ((expectedIdentity && tokenIdentity(data) !== expectedIdentity) ||
          (expectedIdentity && identity !== expectedIdentity))
      ) {
        changedSession();
        throw new SessionChangedError();
      }
      if (data) startSession(data);
      return data;
    });
  }
  register(email: string, name: string, password: string) {
    return this.client
      .POST("/v1/auth/register", { body: { email, name, password } })
      .then(unwrap);
  }
  verifyEmail(token: string, password: string) {
    return this.client
      .POST("/v1/auth/verify-email", { body: { token, password } })
      .then(unwrap);
  }
  async login(email: string, password: string) {
    const data = unwrap(
      await this.client.POST("/v1/auth/login", { body: { email, password } }),
    );
    startSession(data);
    return data;
  }
  async logout() {
    const expected = identity;
    if (!accessToken && !(await this.refresh(expected)))
      throw new Error("Could not confirm sign out. Please try again.");
    try {
      unwrap(await this.client.POST("/v1/auth/logout"));
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 401) throw error;
      if (!(await this.refresh(expected)))
        throw new Error("Could not confirm sign out. Please try again.");
      unwrap(await this.client.POST("/v1/auth/logout"));
    }
    endSession();
  }
  getCurrentUser() {
    return this.client.GET("/v1/me").then(unwrap);
  }
  async getItems(cursor?: string) {
    return {
      data: unwrap(
        await this.client.GET("/v1/items", { params: { query: { cursor } } }),
      ),
    };
  }
  getItem(id: string) {
    return this.client
      .GET("/v1/items/{item_id}", { params: { path: { item_id: id } } })
      .then(unwrap);
  }
  createItem(title: string, description: string) {
    return this.client.POST("/v1/items", { body: { title, description } }).then(unwrap);
  }
  updateItem(id: string, title: string, description: string) {
    return this.client
      .PATCH("/v1/items/{item_id}", {
        params: { path: { item_id: id } },
        body: { title, description },
      })
      .then(unwrap);
  }
  deleteItem(id: string) {
    return this.client
      .DELETE("/v1/items/{item_id}", { params: { path: { item_id: id } } })
      .then(unwrap);
  }
  health() {
    return this.client.GET("/health").then(unwrap);
  }
}
export const api = new ApiClient();

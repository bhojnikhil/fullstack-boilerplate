import axios, { AxiosInstance, InternalAxiosRequestConfig } from "axios";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
// The CSRF token is not a credential on its own: it only works together with the
// httpOnly refresh cookie, and other sites cannot read this origin's storage.
const CSRF_STORAGE_KEY = "csrf_token";

export interface Item {
  id: string;
  title: string;
  description: string | null;
  created_at: string;
}

interface ItemPage {
  items: Item[];
  next_cursor: string | null;
}

export interface User {
  id: string;
  email: string;
  email_verified: boolean;
  name: string;
}

interface TokenResponse {
  access_token: string;
  expires_in: number;
  csrf_token: string | null;
  user: User;
}

type RetriableRequest = InternalAxiosRequestConfig & { _retried?: boolean };

// The access token lives only in memory. The refresh token is an httpOnly cookie
// scoped to /v1/auth/refresh, so page scripts never see it.
let accessToken: string | null = null;
let refreshing: Promise<TokenResponse | null> | null = null;

function storage(): Storage | null {
  try {
    return typeof window !== "undefined" ? window.localStorage : null;
  } catch {
    return null;
  }
}

function startSession(tokens: TokenResponse) {
  accessToken = tokens.access_token;
  if (tokens.csrf_token) storage()?.setItem(CSRF_STORAGE_KEY, tokens.csrf_token);
}

function endSession() {
  accessToken = null;
  storage()?.removeItem(CSRF_STORAGE_KEY);
}

/** Run one refresh at a time across tabs: reusing a rotated refresh token signs out. */
function oneAtATime<T>(task: () => Promise<T>): Promise<T> {
  if (typeof navigator !== "undefined" && "locks" in navigator) {
    return navigator.locks.request("auth-refresh", task);
  }
  return task();
}

class ApiClient {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: API_URL,
      // Sends the refresh cookie to /v1/auth/refresh. X-Platform: web selects cookie delivery.
      withCredentials: true,
      headers: {
        "Content-Type": "application/json",
        "X-Platform": "web",
      },
    });

    this.client.interceptors.request.use((config) => {
      if (accessToken) {
        config.headers.Authorization = `Bearer ${accessToken}`;
      }
      return config;
    });

    // An expired access token gets one silent refresh and a retry.
    this.client.interceptors.response.use(
      (response) => response,
      async (error) => {
        const original = error.config as RetriableRequest | undefined;
        const isAuthCall = original?.url?.startsWith("/v1/auth/") ?? false;
        if (
          error.response?.status === 401 &&
          original &&
          !original._retried &&
          !isAuthCall
        ) {
          original._retried = true;
          if (await this.refresh()) {
            return this.client(original);
          }
          if (typeof window !== "undefined") {
            window.location.href = "/auth/login";
          }
        }
        return Promise.reject(error);
      },
    );
  }

  /** Exchange the refresh cookie for a new access token. Null if signed out. */
  refresh(): Promise<TokenResponse | null> {
    refreshing ??= oneAtATime(async () => {
      const csrfToken = storage()?.getItem(CSRF_STORAGE_KEY);
      if (!csrfToken) return null;
      try {
        const { data } = await this.client.post<TokenResponse>(
          "/v1/auth/refresh",
          undefined,
          {
            headers: { "X-CSRF-Token": csrfToken },
          },
        );
        startSession(data);
        return data;
      } catch {
        endSession();
        return null;
      }
    }).finally(() => {
      refreshing = null;
    });
    return refreshing;
  }

  // Auth endpoints
  register(email: string, name: string, password: string) {
    return this.client.post("/v1/auth/register", { email, name, password });
  }

  async login(email: string, password: string) {
    const { data } = await this.client.post<TokenResponse>("/v1/auth/login", {
      email,
      password,
    });
    startSession(data);
    return data;
  }

  async logout() {
    try {
      if (accessToken) await this.client.post("/v1/auth/logout");
    } finally {
      endSession();
    }
  }

  getCurrentUser() {
    return this.client.get<User>("/v1/me");
  }

  // Items endpoints
  getItems(cursor?: string) {
    return this.client.get<ItemPage>("/v1/items", { params: { cursor } });
  }

  getItem(id: string) {
    return this.client.get(`/v1/items/${id}`);
  }

  createItem(title: string, description: string) {
    return this.client.post("/v1/items", { title, description });
  }

  updateItem(id: string, title: string, description: string) {
    return this.client.patch(`/v1/items/${id}`, { title, description });
  }

  deleteItem(id: string) {
    return this.client.delete(`/v1/items/${id}`);
  }

  // Health check
  health() {
    return this.client.get("/health");
  }
}

export const api = new ApiClient();

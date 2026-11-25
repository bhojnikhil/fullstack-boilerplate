import AsyncStorage from "@react-native-async-storage/async-storage";
import { createApiClient } from "@repo/api-client";

import { getRuntimeEnv } from "./env";
import { getClientHeaders } from "./client-headers";
import { createRefreshRequest, createSessionStore, type SessionStore } from "./session";
import { tokenStorage, type TokenStorage } from "./token-storage";
import { uuid } from "./uuid";

type Api = ReturnType<typeof createApiClient>;

/** Tiny external store, enough for useSyncExternalStore. */
export interface ValueStore<T> {
  get(): T;
  set(value: T): void;
  subscribe(listener: () => void): () => void;
}

export function createValueStore<T>(initial: T): ValueStore<T> {
  let value = initial;
  const listeners = new Set<() => void>();
  return {
    get: () => value,
    set(next) {
      if (Object.is(next, value)) return;
      value = next;
      listeners.forEach((listener) => listener());
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

export interface UpdateRequired {
  minVersion: string | null;
}

export interface AppServices {
  api: Api;
  session: SessionStore;
  /** Active workspace id (sent as X-Workspace-Id), or null. */
  workspaceId: ValueStore<string | null>;
  /** Set when the API answered 426: the app is too old to continue. */
  updateRequired: ValueStore<UpdateRequired | null>;
}

export interface AppServicesOptions {
  baseUrl: string;
  headers: { "X-App-Version": string; "X-Platform": string };
  storage?: TokenStorage;
  fetch?: typeof globalThis.fetch;
}

export function createAppServices(options: AppServicesOptions): AppServices {
  const send = options.fetch ?? ((...args) => globalThis.fetch(...args));
  const session = createSessionStore({
    storage: options.storage ?? tokenStorage,
    requestRefresh: createRefreshRequest({
      baseUrl: options.baseUrl,
      headers: options.headers,
      fetch: send,
    }),
  });
  const workspaceId = createValueStore<string | null>(null);
  const updateRequired = createValueStore<UpdateRequired | null>(null);

  const api = createApiClient({
    baseUrl: options.baseUrl,
    requestId: uuid,
    idempotencyKey: uuid,
    appVersion: options.headers["X-App-Version"],
    platform: options.headers["X-Platform"],
    getAccessToken: () => session.getState().accessToken,
    getSessionId: () => session.getState().sessionId,
    getWorkspaceId: () => workspaceId.get(),
    refresh: (expected) => session.refresh(expected),
    fetch: async (input, init) => {
      const response = await send(input, init);
      if (response.status === 426) {
        let minVersion: string | null = null;
        try {
          const body = (await response.clone().json()) as {
            error?: { details?: { min_supported_app_version?: unknown } };
          };
          const min = body.error?.details?.min_supported_app_version;
          if (typeof min === "string") minVersion = min;
        } catch {
          // Body is optional context only.
        }
        updateRequired.set({ minVersion });
      }
      return response;
    },
  });
  return { api, session, workspaceId, updateRequired };
}

let shared: AppServices | undefined;

/** The app's singleton services (lazy: needs the app config at runtime). */
export function getAppServices(): AppServices {
  shared ??= createAppServices({
    baseUrl: getRuntimeEnv().apiUrl,
    headers: getClientHeaders(),
  });
  return shared;
}

export const ACTIVE_WORKSPACE_KEY_PREFIX = "active-workspace:";

export async function loadActiveWorkspace(accountId: string): Promise<string | null> {
  return AsyncStorage.getItem(`${ACTIVE_WORKSPACE_KEY_PREFIX}${accountId}`);
}

export async function saveActiveWorkspace(
  accountId: string,
  workspaceId: string | null,
): Promise<void> {
  const key = `${ACTIVE_WORKSPACE_KEY_PREFIX}${accountId}`;
  if (workspaceId) await AsyncStorage.setItem(key, workspaceId);
  else await AsyncStorage.removeItem(key);
}

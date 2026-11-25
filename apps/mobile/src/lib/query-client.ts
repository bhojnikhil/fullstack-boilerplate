import AsyncStorage from "@react-native-async-storage/async-storage";
import { createAsyncStoragePersister } from "@tanstack/query-async-storage-persister";
import {
  defaultShouldDehydrateQuery,
  QueryClient,
  type Query,
} from "@tanstack/react-query";
import type { PersistQueryClientOptions } from "@tanstack/react-query-persist-client";

declare module "@tanstack/react-query" {
  interface Register {
    queryMeta: {
      /**
       * Opt-in: only queries with `persist: true` are written to the on-disk
       * cache. AsyncStorage is NOT encrypted; never set this on queries that
       * return secrets or sensitive personal data.
       */
      persist?: boolean;
    };
  }
}

/** How long a persisted cache is trusted after the app was last used. */
export const CACHE_MAX_AGE_MS = 24 * 60 * 60 * 1000;

const STORAGE_KEY_PREFIX = "query-cache:";

/** Cache scope while nobody is signed in. Signed-in scopes are account ids. */
export const SIGNED_OUT_SCOPE = "signed-out";

type Storage = Parameters<typeof createAsyncStoragePersister>[0]["storage"] & {};
type PrunableStorage = Storage &
  Pick<typeof AsyncStorage, "getAllKeys" | "multiRemove">;

/** Each account (scope) gets its own storage entry; caches never cross users. */
export function queryCacheStorageKey(scope: string): string {
  return `${STORAGE_KEY_PREFIX}${scope}`;
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Must be >= maxAge or restored queries are garbage-collected at once.
        gcTime: CACHE_MAX_AGE_MS,
        staleTime: 30_000,
        retry: 2,
      },
      mutations: { retry: 0 },
    },
  });
}

/** Allowlist: successful queries that opted in with `meta: { persist: true }`. */
export function shouldPersistQuery(query: Query): boolean {
  return defaultShouldDehydrateQuery(query) && query.meta?.persist === true;
}

export interface ScopedQueryCacheInput {
  appVersion: string;
  /** Account id, or SIGNED_OUT_SCOPE. */
  scope: string;
  storage?: Storage;
  /** Write throttle (ms); the persister's default is 1000. */
  throttleTime?: number;
}

export interface ScopedQueryCache {
  scope: string;
  /** For PersistQueryClientProvider / persistQueryClient. */
  persistOptions: Omit<PersistQueryClientOptions, "queryClient">;
  /**
   * Stops all further writes for this scope (writes the persister has queued
   * become no-ops) and resolves once writes already in flight have settled.
   * Idempotent.
   */
  retire(): Promise<void>;
  /**
   * Sign-out: retires the scope, drops the in-memory cache and deletes the
   * persisted copy. Nothing queued before or during the call can recreate it.
   */
  clear(queryClient: QueryClient): Promise<void>;
}

/** Retirements still draining; pruning waits for them before deleting. */
const pendingRetirements = new Set<Promise<void>>();

export function createScopedQueryCache({
  appVersion,
  scope,
  storage = AsyncStorage,
  throttleTime,
}: ScopedQueryCacheInput): ScopedQueryCache {
  const key = queryCacheStorageKey(scope);
  const inFlight = new Set<Promise<unknown>>();
  let retirement: Promise<void> | undefined;

  function track<T>(operation: Promise<T>): Promise<T> {
    inFlight.add(operation);
    operation.then(
      () => inFlight.delete(operation),
      () => inFlight.delete(operation),
    );
    return operation;
  }

  // The persister only ever writes through this wrapper.
  const guardedStorage: Storage = {
    getItem: (k) => storage.getItem(k),
    setItem: (k, value) =>
      retirement
        ? Promise.resolve()
        : track(Promise.resolve(storage.setItem(k, value))),
    removeItem: (k) => track(Promise.resolve(storage.removeItem(k))),
  };

  function retire(): Promise<void> {
    if (!retirement) {
      const drained = Promise.allSettled([...inFlight]).then(() => undefined);
      retirement = drained;
      pendingRetirements.add(drained);
      drained.then(() => pendingRetirements.delete(drained));
    }
    return retirement;
  }

  return {
    scope,
    persistOptions: {
      persister: createAsyncStoragePersister({
        storage: guardedStorage,
        key,
        ...(throttleTime === undefined ? {} : { throttleTime }),
      }),
      maxAge: CACHE_MAX_AGE_MS,
      // A new app version (or a cache written for another scope) is discarded
      // instead of being read.
      buster: `${appVersion}|${scope}`,
      dehydrateOptions: {
        shouldDehydrateQuery: shouldPersistQuery,
        // Mutations are never written to disk: their variables can hold
        // passwords or other input that must not sit in plaintext storage.
        shouldDehydrateMutation: () => false,
      },
    },
    retire,
    async clear(queryClient) {
      await retire();
      queryClient.clear();
      await storage.removeItem(key);
    },
  };
}

/**
 * Deletes persisted caches of every scope except `keepScope` (e.g. a previous
 * account's). Waits for retiring scopes to drain first, so a retired scope's
 * in-flight write can't land after its entry was deleted.
 */
export async function pruneOtherQueryCaches(
  keepScope: string,
  storage: PrunableStorage = AsyncStorage,
): Promise<void> {
  await Promise.allSettled([...pendingRetirements]);
  const keep = queryCacheStorageKey(keepScope);
  const stale = (await storage.getAllKeys()).filter(
    (key) => key.startsWith(STORAGE_KEY_PREFIX) && key !== keep,
  );
  if (stale.length > 0) await storage.multiRemove(stale);
}

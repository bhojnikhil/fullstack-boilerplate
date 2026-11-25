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

export interface PersistOptionsInput {
  appVersion: string;
  /** Account id, or SIGNED_OUT_SCOPE. */
  scope: string;
  storage?: Storage;
  /** Write throttle (ms); the persister's default is 1000. */
  throttleTime?: number;
}

export function createPersistOptions({
  appVersion,
  scope,
  storage = AsyncStorage,
  throttleTime,
}: PersistOptionsInput): Omit<PersistQueryClientOptions, "queryClient"> {
  return {
    persister: createAsyncStoragePersister({
      storage,
      key: queryCacheStorageKey(scope),
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
  };
}

/** For sign-out: drops the in-memory cache and deletes the scope's persisted copy. */
export async function clearQueryCache(
  queryClient: QueryClient,
  scope: string,
  storage: Storage = AsyncStorage,
): Promise<void> {
  queryClient.clear();
  await storage.removeItem(queryCacheStorageKey(scope));
}

/** Deletes persisted caches of every scope except `keepScope` (e.g. a previous account's). */
export async function pruneOtherQueryCaches(
  keepScope: string,
  storage: PrunableStorage = AsyncStorage,
): Promise<void> {
  const keep = queryCacheStorageKey(keepScope);
  const stale = (await storage.getAllKeys()).filter(
    (key) => key.startsWith(STORAGE_KEY_PREFIX) && key !== keep,
  );
  if (stale.length > 0) await storage.multiRemove(stale);
}

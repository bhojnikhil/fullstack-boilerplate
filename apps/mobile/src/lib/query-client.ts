import AsyncStorage from "@react-native-async-storage/async-storage";
import { createAsyncStoragePersister } from "@tanstack/query-async-storage-persister";
import {
  defaultShouldDehydrateQuery,
  QueryClient,
  type Query,
} from "@tanstack/react-query";
import type { PersistQueryClientOptions } from "@tanstack/react-query-persist-client";

/** How long a persisted cache is trusted after the app was last used. */
export const CACHE_MAX_AGE_MS = 24 * 60 * 60 * 1000;

export const QUERY_CACHE_STORAGE_KEY = "query-cache";

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

/**
 * The persisted cache lives in AsyncStorage, which is NOT encrypted. Queries
 * holding sensitive data must opt out with `meta: { persist: false }`, and
 * sign-out must clear the cache (phase 9b).
 */
export function shouldPersistQuery(query: Query): boolean {
  return defaultShouldDehydrateQuery(query) && query.meta?.persist !== false;
}

export function createPersistOptions(
  buster: string,
  storage: Parameters<typeof createAsyncStoragePersister>[0]["storage"] = AsyncStorage,
): Omit<PersistQueryClientOptions, "queryClient"> {
  return {
    persister: createAsyncStoragePersister({ storage, key: QUERY_CACHE_STORAGE_KEY }),
    maxAge: CACHE_MAX_AGE_MS,
    // A new app version discards the cache instead of reading stale shapes.
    buster,
    dehydrateOptions: { shouldDehydrateQuery: shouldPersistQuery },
  };
}

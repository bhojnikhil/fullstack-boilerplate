import { useQueryClient } from "@tanstack/react-query";
import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import { getRuntimeEnv } from "@/lib/env";
import { connectQueryManagers } from "@/lib/network";
import {
  createQueryClient,
  createScopedQueryCache,
  pruneOtherQueryCaches,
  SIGNED_OUT_SCOPE,
  type ScopedQueryCache,
} from "@/lib/query-client";

const ScopedQueryCacheContext = createContext<ScopedQueryCache | null>(null);

/**
 * For sign-out (phase 9b): stops this account's cache writes, clears it from
 * memory and deletes its persisted copy.
 */
export function useClearQueryCache(): () => Promise<void> {
  const cache = useContext(ScopedQueryCacheContext);
  const queryClient = useQueryClient();
  return useCallback(async () => {
    if (!cache) throw new Error("useClearQueryCache must be used inside AppProviders");
    await cache.clear(queryClient);
  }, [cache, queryClient]);
}

function QueryProvider({ scope, children }: { scope: string; children: ReactNode }) {
  const [queryClient] = useState(createQueryClient);
  const [cache] = useState(() =>
    createScopedQueryCache({ appVersion: getRuntimeEnv().appVersion, scope }),
  );

  useEffect(() => {
    // Another account's cache must not linger on disk after switching. React
    // runs the previous scope's cleanup (retire) before this effect, and
    // pruning waits for that retirement to drain.
    pruneOtherQueryCaches(scope).catch(() => undefined);
    return () => {
      cache.retire().catch(() => undefined);
    };
  }, [cache, scope]);

  return (
    <PersistQueryClientProvider
      client={queryClient}
      persistOptions={cache.persistOptions}
    >
      <ScopedQueryCacheContext.Provider value={cache}>
        {children}
      </ScopedQueryCacheContext.Provider>
    </PersistQueryClientProvider>
  );
}

interface AppProvidersProps {
  children: ReactNode;
  /**
   * Query cache scope: the signed-in account id, or SIGNED_OUT_SCOPE. A new
   * scope remounts the tree with a fresh query client and its own persisted
   * cache, so data never crosses accounts. (Auth arrives in phase 9b; its
   * sign-out must also call useClearQueryCache().)
   */
  cacheScope?: string;
}

/** App-wide providers. Safe-area and navigation providers come from Expo Router. */
export function AppProviders({
  children,
  cacheScope = SIGNED_OUT_SCOPE,
}: AppProvidersProps) {
  useEffect(() => connectQueryManagers(), []);

  return (
    <QueryProvider key={cacheScope} scope={cacheScope}>
      {children}
    </QueryProvider>
  );
}

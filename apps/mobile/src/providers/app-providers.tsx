import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client";
import { useEffect, useState, type ReactNode } from "react";

import { getRuntimeEnv } from "@/lib/env";
import { connectQueryManagers } from "@/lib/network";
import {
  createPersistOptions,
  createQueryClient,
  pruneOtherQueryCaches,
  SIGNED_OUT_SCOPE,
} from "@/lib/query-client";

function QueryProvider({ scope, children }: { scope: string; children: ReactNode }) {
  const [queryClient] = useState(createQueryClient);
  const [persistOptions] = useState(() =>
    createPersistOptions({ appVersion: getRuntimeEnv().appVersion, scope }),
  );

  // Another account's cache must not linger on disk after switching.
  useEffect(() => {
    pruneOtherQueryCaches(scope).catch(() => undefined);
  }, [scope]);

  return (
    <PersistQueryClientProvider client={queryClient} persistOptions={persistOptions}>
      {children}
    </PersistQueryClientProvider>
  );
}

interface AppProvidersProps {
  children: ReactNode;
  /**
   * Query cache scope: the signed-in account id, or SIGNED_OUT_SCOPE. A new
   * scope remounts the tree with a fresh query client and its own persisted
   * cache, so data never crosses accounts. (Auth arrives in phase 9b; its
   * sign-out must also call clearQueryCache.)
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

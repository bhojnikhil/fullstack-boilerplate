import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client";
import { useEffect, useState, type ReactNode } from "react";

import { getRuntimeEnv } from "@/lib/env";
import { connectQueryManagers } from "@/lib/network";
import { createPersistOptions, createQueryClient } from "@/lib/query-client";

/** App-wide providers. Safe-area and navigation providers come from Expo Router. */
export function AppProviders({ children }: { children: ReactNode }) {
  const [queryClient] = useState(createQueryClient);
  const [persistOptions] = useState(() =>
    createPersistOptions(getRuntimeEnv().appVersion),
  );

  useEffect(() => connectQueryManagers(), []);

  return (
    <PersistQueryClientProvider client={queryClient} persistOptions={persistOptions}>
      {children}
    </PersistQueryClientProvider>
  );
}

import { createContext, useContext, useSyncExternalStore, type ReactNode } from "react";

import { getAppServices, type AppServices } from "@/lib/app-services";
import type { SessionState } from "@/lib/session";

const ServicesContext = createContext<AppServices | null>(null);

/** Provides the API client and session; tests pass their own services. */
export function ServicesProvider({
  services,
  children,
}: {
  services?: AppServices;
  children: ReactNode;
}) {
  return (
    <ServicesContext.Provider value={services ?? getAppServices()}>
      {children}
    </ServicesContext.Provider>
  );
}

export function useServices(): AppServices {
  const services = useContext(ServicesContext);
  if (!services) throw new Error("useServices must be used inside ServicesProvider");
  return services;
}

export function useSession(): SessionState {
  const { session } = useServices();
  return useSyncExternalStore(session.subscribe, session.getState, session.getState);
}

export function useActiveWorkspaceId(): string | null {
  const { workspaceId } = useServices();
  return useSyncExternalStore(workspaceId.subscribe, workspaceId.get, workspaceId.get);
}

export function useUpdateRequired() {
  const { updateRequired } = useServices();
  return useSyncExternalStore(
    updateRequired.subscribe,
    updateRequired.get,
    updateRequired.get,
  );
}

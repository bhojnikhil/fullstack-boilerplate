import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { useActiveWorkspaceId, useServices, useSession } from "@/providers/services";

import { workspaceApi } from "./workspace-api";

export function useWorkspaces() {
  const { api } = useServices();
  const { accountId } = useSession();
  const client = useMemo(() => workspaceApi(api), [api]);
  return useQuery({
    queryKey: ["workspaces", accountId],
    enabled: accountId !== null,
    queryFn: () => client.list(),
    meta: { persist: true },
  });
}

export function useWorkspaceClient() {
  const { api } = useServices();
  return useMemo(() => workspaceApi(api), [api]);
}

export function useActiveWorkspace() {
  const id = useActiveWorkspaceId();
  const query = useWorkspaces();
  return {
    ...query,
    active: query.data?.find((workspace) => workspace.id === id) ?? null,
  };
}

import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";

import { useActiveWorkspaceId, useServices, useSession } from "@/providers/services";

import { workspaceApi } from "./workspace-api";

export function useWorkspaces() {
  const { api, workspaceId, removedWorkspace } = useServices();
  const id = useActiveWorkspaceId();
  const { accountId } = useSession();
  const client = useMemo(() => workspaceApi(api), [api]);
  const query = useQuery({
    queryKey: ["workspaces", accountId],
    enabled: accountId !== null,
    queryFn: () => client.list(),
    meta: { persist: true },
  });
  useEffect(() => {
    if (
      id &&
      query.isFetchedAfterMount &&
      query.isSuccess &&
      !query.data.some((workspace) => workspace.id === id)
    ) {
      workspaceId.set(null);
      removedWorkspace.set(id);
    }
  }, [
    id,
    query.data,
    query.isFetchedAfterMount,
    query.isSuccess,
    workspaceId,
    removedWorkspace,
  ]);
  return query;
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

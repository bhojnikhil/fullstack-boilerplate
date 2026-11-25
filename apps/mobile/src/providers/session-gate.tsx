import { useEffect, type ReactNode } from "react";

import { loadActiveWorkspace, saveActiveWorkspace } from "@/lib/app-services";
import { pruneOtherQueues } from "@/lib/mutation-queue";
import { SIGNED_OUT_SCOPE } from "@/lib/query-client";

import { AppProviders } from "./app-providers";
import { useServices, useSession } from "./services";

/**
 * Loads the stored session once, then scopes everything per account: a new
 * account id remounts the query client with its own persisted cache, and the
 * previous account's offline queue is deleted from disk.
 */
export function SessionGate({ children }: { children: ReactNode }) {
  const { session, workspaceId } = useServices();
  const { status, accountId } = useSession();

  useEffect(() => {
    session.load().catch(() => undefined);
  }, [session]);

  useEffect(() => {
    if (status === "loading") return;
    pruneOtherQueues(accountId).catch(() => undefined);
    if (!accountId) {
      workspaceId.set(null);
      return;
    }
    let cancelled = false;
    loadActiveWorkspace(accountId)
      .then((saved) => {
        if (!cancelled) workspaceId.set(saved);
      })
      .catch(() => undefined);
    const stop = workspaceId.subscribe(() => {
      if (!cancelled)
        saveActiveWorkspace(accountId, workspaceId.get()).catch(() => undefined);
    });
    return () => {
      cancelled = true;
      stop();
    };
  }, [status, accountId, workspaceId]);

  return (
    <AppProviders cacheScope={accountId ?? SIGNED_OUT_SCOPE}>{children}</AppProviders>
  );
}

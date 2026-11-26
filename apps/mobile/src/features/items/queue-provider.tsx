import { onlineManager, useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { AppState } from "react-native";

import { SessionChangedError } from "@repo/api-client";

import { apiErrorFromResult, isNetworkError } from "@/lib/api-error";
import {
  createMutationQueue,
  type MutationQueue,
  type QueuedMutation,
  type SendOutcome,
} from "@/lib/mutation-queue";
import { useServices, useSession } from "@/providers/services";

const QueueContext = createContext<MutationQueue | null>(null);

export function useMutationQueue(): MutationQueue {
  const queue = useContext(QueueContext);
  if (!queue) throw new Error("useMutationQueue must be used inside QueueProvider");
  return queue;
}

export function useMutationQueueOptional(): MutationQueue | null {
  return useContext(QueueContext);
}

/** Re-renders when the queue changes. */
export function useQueuedMutations(): readonly QueuedMutation[] {
  const queue = useMutationQueue();
  return useSyncExternalStore(queue.subscribe, queue.entries, queue.entries);
}

export function useQueueFailures() {
  const queue = useMutationQueue();
  return useSyncExternalStore(queue.subscribe, queue.failures, queue.failures);
}

/** Retry later: offline, throttled, server trouble. Anything else will never succeed. */
export function classifyStatus(status: number, code: string): SendOutcome {
  if (status >= 200 && status < 300) return "done";
  if (status === 401 || status === 408 || status === 425 || status === 426)
    return "retry";
  if (status === 429 || status >= 500) return "retry";
  if (status === 409 && code === "idempotency_in_progress") return "retry";
  return "rejected";
}

const RETRY_INTERVAL_MS = 30_000;

export function QueueProvider({ children }: { children: ReactNode }) {
  const { api, session } = useServices();
  const { accountId, sessionId } = useSession();
  const queryClient = useQueryClient();

  const queue = useMemo(() => {
    if (!accountId || !sessionId) return null;
    return createMutationQueue({
      accountId,
      onApplied: () => {
        queryClient.invalidateQueries({ queryKey: ["items"] }).catch(() => undefined);
      },
      send: async (mutation) => {
        const current = session.getState();
        if (current.accountId !== accountId || current.sessionId !== sessionId)
          return "retry";
        if (!mutation.workspaceId) return { rejected: "Missing workspace" };
        // The recorded Idempotency-Key and workspace are replayed verbatim.
        const headers: Record<string, string> = { "Idempotency-Key": mutation.key };
        headers["X-Workspace-Id"] = mutation.workspaceId;
        try {
          const result =
            mutation.kind === "item.create"
              ? await api.POST("/v1/items", { body: mutation.body, headers })
              : await api.PATCH("/v1/items/{item_id}", {
                  params: { path: { item_id: mutation.itemId } },
                  body: mutation.body,
                  headers,
                });
          if (result.response.ok) {
            if (mutation.kind === "item.create" && result.data && "id" in result.data)
              return { appliedId: result.data.id };
            return mutation.kind === "item.create" ? "retry" : "done";
          }
          const error = apiErrorFromResult(result);
          const outcome = classifyStatus(error.status, error.code);
          return outcome === "rejected" ? { rejected: error.message } : outcome;
        } catch (error) {
          if (isNetworkError(error) || error instanceof SessionChangedError)
            return "retry";
          throw error;
        }
      },
    });
  }, [accountId, sessionId, api, queryClient, session]);

  useEffect(() => {
    if (!queue) return;
    let active = true;
    const retireIfChanged = () => {
      const current = session.getState();
      if (current.accountId !== accountId || current.sessionId !== sessionId) {
        active = false;
        void queue.clear();
      }
    };
    const offSession = session.subscribe(retireIfChanged);
    retireIfChanged();
    const flush = () => {
      if (active && onlineManager.isOnline()) queue.flush().catch(() => undefined);
    };
    queue
      .load()
      .then(flush)
      .catch(() => undefined);
    // Replay when connectivity returns, when the app comes back to the
    // foreground, and whenever something is added.
    const offOnline = onlineManager.subscribe((online) => {
      if (online) flush();
    });
    const appState = AppState.addEventListener("change", (state) => {
      if (state === "active") flush();
    });
    const offQueue = queue.subscribe(flush);
    // A failed attempt (server trouble) is retried even without a connectivity event.
    const timer = setInterval(() => {
      if (queue.entries().length > 0) flush();
    }, RETRY_INTERVAL_MS);
    return () => {
      active = false;
      clearInterval(timer);
      offSession();
      offOnline();
      appState.remove();
      offQueue();
    };
  }, [queue, session, accountId, sessionId]);

  return <QueueContext.Provider value={queue}>{children}</QueueContext.Provider>;
}

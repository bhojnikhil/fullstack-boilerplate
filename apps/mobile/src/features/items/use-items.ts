import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "@repo/api-client";
import { useMemo } from "react";

import { ApiError, unwrap } from "@/lib/api-error";
import type { ItemFields, QueuedMutation } from "@/lib/mutation-queue";
import { useActiveWorkspaceId, useServices, useSession } from "@/providers/services";

import { useMutationQueue, useQueuedMutations } from "./queue-provider";

export interface ServerItem {
  id: string;
  title: string;
  description: string | null;
  is_active: boolean;
  created_at: string;
}

export interface DisplayItem extends ServerItem {
  /** Not yet confirmed by the server (queued create or edit). */
  pending: boolean;
  /** A queued create: the id is local to this device. */
  local: boolean;
  /** Id of the queue entry behind a local item. */
  queueId?: string;
}

type ItemPage = components["schemas"]["ItemPage"];

const PAGE_SIZE = 100;
const MAX_PAGES = 20;
export const LOCAL_PREFIX = "local:";

export function itemsQueryKey(accountId: string | null, workspaceId: string | null) {
  return ["items", accountId, workspaceId] as const;
}

/**
 * Applies queued writes on top of the server list, so a create or edit shows
 * immediately and survives going offline: queued creates come first, queued
 * edits patch the matching server item.
 */
export function overlayQueue(
  server: readonly ServerItem[],
  queued: readonly QueuedMutation[],
  workspaceId: string | null,
): DisplayItem[] {
  const mine = queued.filter((entry) => entry.workspaceId === workspaceId);
  const patches = new Map<string, Partial<ItemFields> & { is_active?: boolean }>();
  for (const entry of mine) {
    if (entry.kind === "item.update") {
      patches.set(entry.itemId, { ...patches.get(entry.itemId), ...entry.body });
    }
  }
  const created: DisplayItem[] = mine
    .filter((entry) => entry.kind === "item.create")
    .map((entry) => ({
      id: `${LOCAL_PREFIX}${entry.id}`,
      title: entry.pendingEdit?.title ?? entry.body.title,
      description:
        entry.pendingEdit?.description !== undefined
          ? entry.pendingEdit.description
          : entry.body.description,
      is_active: true,
      created_at: new Date(entry.createdAt).toISOString(),
      pending: true,
      local: true,
      queueId: entry.id,
    }))
    .reverse();
  const synced = server.map((item) => {
    const patch = patches.get(item.id);
    return {
      ...item,
      ...patch,
      pending: patch !== undefined,
      local: false,
    };
  });
  return [...created, ...synced];
}

export function useItems() {
  const { api } = useServices();
  const { accountId } = useSession();
  const workspaceId = useActiveWorkspaceId();
  const queued = useQueuedMutations();

  const query = useQuery({
    queryKey: itemsQueryKey(accountId, workspaceId),
    enabled: accountId !== null,
    // Item titles are not secret; opt this list into the on-disk cache.
    meta: { persist: true },
    queryFn: async (): Promise<ServerItem[]> => {
      const all: ServerItem[] = [];
      let cursor: string | null = null;
      for (let page = 0; page < MAX_PAGES; page += 1) {
        const result: ItemPage = await unwrap(
          api.GET("/v1/items", {
            params: { query: { limit: PAGE_SIZE, ...(cursor ? { cursor } : {}) } },
          }),
        );
        all.push(...result.items);
        cursor = result.next_cursor;
        if (!cursor) break;
      }
      return all;
    },
  });

  const items = useMemo(
    () => overlayQueue(query.data ?? [], queued, workspaceId),
    [query.data, queued, workspaceId],
  );
  return { ...query, items };
}

export function useItem(id: string) {
  const { items } = useItems();
  return items.find((item) => item.id === id) ?? null;
}

export function useSaveItem() {
  const queue = useMutationQueue();
  const workspaceId = useActiveWorkspaceId();
  return {
    /** Queues the create; the list shows it at once and it syncs when online. */
    create: (fields: ItemFields) =>
      queue.enqueue({ kind: "item.create", workspaceId, body: fields }),
    /** Edits a synced item, or the pending create behind a local one. */
    async update(item: DisplayItem, fields: Partial<ItemFields>) {
      if (item.local && item.queueId) {
        const patched = await queue.patchCreate(item.queueId, fields);
        if (!patched)
          throw new Error("This item is being saved. Try again in a moment.");
        return;
      }
      await queue.enqueue({
        kind: "item.update",
        workspaceId,
        itemId: item.id,
        body: fields,
      });
    },
  };
}

export function useDeleteItem() {
  const { api } = useServices();
  const { accountId } = useSession();
  const workspaceId = useActiveWorkspaceId();
  const queryClient = useQueryClient();
  const queue = useMutationQueue();
  const key = itemsQueryKey(accountId, workspaceId);

  return useMutation({
    mutationFn: async (item: DisplayItem) => {
      if (item.local && item.queueId) {
        await queue.remove(item.queueId);
        return;
      }
      await queue.removeUpdatesFor(item.id);
      try {
        await unwrap(
          api.DELETE("/v1/items/{item_id}", { params: { path: { item_id: item.id } } }),
        );
      } catch (error) {
        // Already gone on the server: the goal is reached.
        if (!(error instanceof ApiError && error.status === 404)) throw error;
      }
    },
    onMutate: async (item) => {
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<ServerItem[]>(key);
      queryClient.setQueryData<ServerItem[]>(key, (old) =>
        old?.filter((existing) => existing.id !== item.id),
      );
      return { previous };
    },
    onError: (_error, _item, context) => {
      if (context?.previous) queryClient.setQueryData(key, context.previous);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: key }),
  });
}

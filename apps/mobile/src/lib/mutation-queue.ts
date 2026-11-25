import AsyncStorage from "@react-native-async-storage/async-storage";

import { uuid } from "./uuid";

/**
 * Persisted queue of item writes made while offline (or in flight), replayed
 * in order. Design rules:
 * - Closed set of mutation kinds with plain data only. It lives in
 *   (unencrypted) AsyncStorage, so it never holds credentials or tokens, and
 *   the TanStack mutation cache is never persisted (see query-client.ts).
 * - One Idempotency-Key per entry, generated once at enqueue time and re-sent
 *   on every replay, so a replay after a lost response cannot duplicate.
 * - One queue per account; entries remember the workspace they were made in.
 */
export interface ItemFields {
  title: string;
  description: string | null;
}

export type QueuedMutation =
  | {
      kind: "item.create";
      id: string;
      key: string;
      workspaceId: string | null;
      createdAt: number;
      body: ItemFields;
    }
  | {
      kind: "item.update";
      id: string;
      key: string;
      workspaceId: string | null;
      createdAt: number;
      itemId: string;
      body: Partial<ItemFields> & { is_active?: boolean };
    };

type DistributiveOmit<T, K extends keyof T> = T extends unknown ? Omit<T, K> : never;
/** A mutation as the caller describes it; the queue adds id, key and time. */
export type NewMutation = DistributiveOmit<QueuedMutation, "id" | "key" | "createdAt">;

/** What a send attempt concluded. */
export type SendOutcome =
  /** Applied (or already applied, per the idempotency key). */
  | "done"
  /** The server will never accept it (404, 422...): drop it and tell the user. */
  | "rejected"
  /** Not now (offline, 5xx, 429): keep it and stop; try again later. */
  | "retry";

export interface QueueFailure {
  mutation: QueuedMutation;
  reason: string;
}

export interface MutationQueue {
  entries(): readonly QueuedMutation[];
  failures(): readonly QueueFailure[];
  subscribe(listener: () => void): () => void;
  load(): Promise<void>;
  enqueue(mutation: NewMutation): Promise<QueuedMutation>;
  /** Edits a not-yet-sent create in place (so an edit of a pending item is one request). */
  patchCreate(id: string, body: Partial<ItemFields>): Promise<boolean>;
  remove(id: string): Promise<void>;
  /** Drops queued updates of an item (it is being deleted). */
  removeUpdatesFor(itemId: string): Promise<void>;
  dismissFailures(): void;
  isSending(id: string): boolean;
  /** Sends queued entries in order until one asks to retry. Overlapping calls share one run. */
  flush(): Promise<void>;
  /** Deletes the persisted copy and forgets everything (sign-out). */
  clear(): Promise<void>;
}

export const QUEUE_KEY_PREFIX = "mutation-queue:v1:";
export const queueStorageKey = (accountId: string) => `${QUEUE_KEY_PREFIX}${accountId}`;

type Storage = Pick<typeof AsyncStorage, "getItem" | "setItem" | "removeItem">;

function newId(): string {
  return uuid();
}

function isFields(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/** Keeps only well-formed entries; anything else in storage is ignored. */
export function parseQueue(raw: string | null): QueuedMutation[] {
  if (!raw) return [];
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return [];
  }
  if (!Array.isArray(data)) return [];
  const valid: QueuedMutation[] = [];
  for (const entry of data as unknown[]) {
    if (!isFields(entry)) continue;
    const { kind, id, key, createdAt, workspaceId, body, itemId } = entry;
    if (typeof id !== "string" || typeof key !== "string") continue;
    if (typeof createdAt !== "number") continue;
    if (workspaceId !== null && typeof workspaceId !== "string") continue;
    if (!isFields(body)) continue;
    if (kind === "item.create") {
      if (typeof body.title !== "string") continue;
      const description =
        typeof body.description === "string" ? body.description : null;
      valid.push({
        kind,
        id,
        key,
        createdAt,
        workspaceId,
        body: { title: body.title, description },
      });
    } else if (kind === "item.update" && typeof itemId === "string") {
      const next: QueuedMutation["body"] = {};
      if (typeof body.title === "string") next.title = body.title;
      if (typeof body.description === "string" || body.description === null) {
        next.description = body.description as string | null;
      }
      if (typeof body.is_active === "boolean") {
        (next as { is_active?: boolean }).is_active = body.is_active;
      }
      valid.push({ kind, id, key, createdAt, workspaceId, itemId, body: next });
    }
  }
  return valid;
}

export function createMutationQueue(options: {
  accountId: string;
  send: (mutation: QueuedMutation) => Promise<SendOutcome | { rejected: string }>;
  /** Called after each applied entry (e.g. to refetch the list). */
  onApplied?: (mutation: QueuedMutation) => void;
  storage?: Storage;
}): MutationQueue {
  const storage = options.storage ?? AsyncStorage;
  const key = queueStorageKey(options.accountId);
  let queue: QueuedMutation[] = [];
  let failed: QueueFailure[] = [];
  let sending: string | null = null;
  let running: Promise<void> | null = null;
  let cleared = false;
  let writes: Promise<unknown> = Promise.resolve();
  const listeners = new Set<() => void>();

  const notify = () => listeners.forEach((listener) => listener());
  const persist = () => {
    if (cleared) return writes;
    const snapshot = JSON.stringify(queue);
    writes = writes
      .catch(() => undefined)
      .then(() => (cleared ? undefined : storage.setItem(key, snapshot)));
    return writes;
  };
  const commit = async (next: QueuedMutation[]) => {
    queue = next;
    notify();
    await persist();
  };

  async function run(): Promise<void> {
    while (!cleared) {
      const head = queue[0];
      if (!head) return;
      sending = head.id;
      let outcome: Awaited<ReturnType<typeof options.send>>;
      try {
        outcome = await options.send(head);
      } catch {
        outcome = "retry"; // network failure, or the session changed mid-flight
      } finally {
        sending = null;
      }
      if (cleared) return;
      if (outcome === "retry") return;
      if (outcome !== "done") {
        const reason = typeof outcome === "string" ? "rejected" : outcome.rejected;
        failed = [...failed, { mutation: head, reason }];
      }
      await commit(queue.filter((entry) => entry.id !== head.id));
      if (outcome === "done") options.onApplied?.(head);
    }
  }

  return {
    entries: () => queue,
    failures: () => failed,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    async load() {
      queue = parseQueue(await storage.getItem(key));
      notify();
    },
    async enqueue(mutation) {
      const entry = {
        ...mutation,
        id: newId(),
        key: newId(),
        createdAt: Date.now(),
      } as QueuedMutation;
      await commit([...queue, entry]);
      return entry;
    },
    async patchCreate(id, body) {
      const target = queue.find((entry) => entry.id === id);
      if (!target || target.kind !== "item.create" || sending === id) return false;
      await commit(
        queue.map((entry) =>
          entry.id === id && entry.kind === "item.create"
            ? { ...entry, body: { ...entry.body, ...body } }
            : entry,
        ),
      );
      return true;
    },
    async remove(id) {
      if (sending === id) return;
      await commit(queue.filter((entry) => entry.id !== id));
    },
    async removeUpdatesFor(itemId) {
      await commit(
        queue.filter(
          (entry) =>
            !(
              entry.kind === "item.update" &&
              entry.itemId === itemId &&
              sending !== entry.id
            ),
        ),
      );
    },
    dismissFailures() {
      failed = [];
      notify();
    },
    isSending: (id) => sending === id,
    flush() {
      running ??= run().finally(() => {
        running = null;
      });
      return running;
    },
    async clear() {
      cleared = true;
      queue = [];
      failed = [];
      notify();
      await writes.catch(() => undefined);
      await storage.removeItem(key);
    },
  };
}

/** Deletes every account's persisted queue except `keepAccountId`'s. */
export async function pruneOtherQueues(
  keepAccountId: string | null,
  storage: Pick<typeof AsyncStorage, "getAllKeys" | "multiRemove"> = AsyncStorage,
): Promise<void> {
  const keep = keepAccountId ? queueStorageKey(keepAccountId) : null;
  const stale = (await storage.getAllKeys()).filter(
    (k) => k.startsWith(QUEUE_KEY_PREFIX) && k !== keep,
  );
  if (stale.length > 0) await storage.multiRemove(stale);
}

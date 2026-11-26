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
      attempted?: boolean;
      pendingEdit?: Partial<ItemFields>;
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
  | { appliedId: string }
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
    if (typeof workspaceId !== "string" || !workspaceId) continue;
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
        attempted: entry.attempted !== false,
        ...(isFields(entry.pendingEdit)
          ? { pendingEdit: entry.pendingEdit as Partial<ItemFields> }
          : {}),
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

const pendingClears = new Map<string, Promise<void>>();

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
  let operations: Promise<unknown> = Promise.resolve();
  const serial = <T>(fn: () => Promise<T>): Promise<T> => {
    const barrier = pendingClears.get(key);
    const task = async () => {
      await barrier;
      return fn();
    };
    const result = operations.then(task, task);
    operations = result.catch(() => undefined);
    return result;
  };
  const listeners = new Set<() => void>();

  const notify = () => listeners.forEach((listener) => listener());
  const commit = async (next: QueuedMutation[]) => {
    if (cleared) throw new Error("Queue retired");
    const snapshot = JSON.stringify(next);
    writes = writes
      .catch(() => undefined)
      .then(() => {
        if (cleared) throw new Error("Queue retired");
        return storage.setItem(key, snapshot);
      });
    await writes;
    if (cleared) throw new Error("Queue retired");
    queue = next;
    notify();
  };

  async function run(): Promise<void> {
    while (!cleared) {
      const head = await serial(async () => {
        const current = queue[0];
        if (!current || cleared) return null;
        if (current.kind === "item.create" && !current.attempted) {
          const frozen = { ...current, attempted: true };
          await commit([frozen, ...queue.slice(1)]);
          return frozen;
        }
        return current;
      });
      if (!head || cleared) return;
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
      if (
        outcome !== "done" &&
        !(typeof outcome === "object" && "appliedId" in outcome)
      ) {
        const reason = typeof outcome === "string" ? "rejected" : outcome.rejected;
        failed = [...failed, { mutation: head, reason }];
      }
      await serial(async () => {
        if (cleared) return;
        const current = queue.find((entry) => entry.id === head.id);
        const rest = queue.filter((entry) => entry.id !== head.id);
        if (
          current?.kind === "item.create" &&
          current.pendingEdit &&
          typeof outcome === "object" &&
          "appliedId" in outcome
        ) {
          rest.unshift({
            kind: "item.update",
            id: newId(),
            key: newId(),
            createdAt: Date.now(),
            workspaceId: current.workspaceId,
            itemId: outcome.appliedId,
            body: current.pendingEdit,
          });
        }
        await commit(rest);
      });
      if (outcome === "done" || (typeof outcome === "object" && "appliedId" in outcome))
        options.onApplied?.(head);
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
      await serial(async () => {
        const loaded = parseQueue(await storage.getItem(key));
        if (!cleared) {
          queue = loaded;
          notify();
        }
      });
    },
    async enqueue(mutation) {
      if (!mutation.workspaceId) throw new Error("Select a workspace before saving.");
      const entry = {
        ...mutation,
        id: newId(),
        key: newId(),
        createdAt: Date.now(),
        ...(mutation.kind === "item.create" ? { attempted: false } : {}),
      } as QueuedMutation;
      await serial(() => commit([...queue, entry]));
      return entry;
    },
    async patchCreate(id, body) {
      return serial(async () => {
        const target = queue.find((entry) => entry.id === id);
        if (!target || target.kind !== "item.create") return false;
        await commit(
          queue.map((entry) =>
            entry.id !== id || entry.kind !== "item.create"
              ? entry
              : entry.attempted
                ? { ...entry, pendingEdit: { ...entry.pendingEdit, ...body } }
                : { ...entry, body: { ...entry.body, ...body } },
          ),
        );
        return true;
      });
    },
    async remove(id) {
      await serial(async () => {
        if (sending !== id) await commit(queue.filter((entry) => entry.id !== id));
      });
    },
    async removeUpdatesFor(itemId) {
      await serial(() =>
        commit(
          queue.filter(
            (entry) =>
              !(
                entry.kind === "item.update" &&
                entry.itemId === itemId &&
                sending !== entry.id
              ),
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
    clear() {
      cleared = true;
      queue = [];
      failed = [];
      notify();
      const previous = pendingClears.get(key);
      const cleanup = (async () => {
        await previous?.catch(() => undefined);
        await operations.catch(() => undefined);
        await writes.catch(() => undefined);
        await storage.removeItem(key);
      })();
      pendingClears.set(key, cleanup);
      void cleanup
        .finally(() => {
          if (pendingClears.get(key) === cleanup) pendingClears.delete(key);
        })
        .catch(() => undefined);
      return cleanup;
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

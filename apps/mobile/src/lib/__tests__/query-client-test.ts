import { QueryClient } from "@tanstack/react-query";
import {
  persistQueryClientRestore,
  persistQueryClientSave,
} from "@tanstack/react-query-persist-client";

import {
  createQueryClient,
  createScopedQueryCache,
  pruneOtherQueryCaches,
  queryCacheStorageKey,
  SIGNED_OUT_SCOPE,
} from "../query-client";

const SENTINEL = "s3cr3t-SENTINEL";

// Clients keep 24 h garbage-collection timers; clear them so Jest can exit.
const clients: QueryClient[] = [];
function newClient(): QueryClient {
  const client = createQueryClient();
  clients.push(client);
  return client;
}
afterEach(() => {
  for (const client of clients.splice(0)) client.clear();
});

function memoryStorage() {
  const data = new Map<string, string>();
  return {
    data,
    getItem: async (key: string) => data.get(key) ?? null,
    setItem: async (key: string, value: string) => {
      data.set(key, value);
    },
    removeItem: async (key: string) => {
      data.delete(key);
    },
    getAllKeys: async () => [...data.keys()],
    multiRemove: async (keys: readonly string[]) => {
      for (const key of keys) data.delete(key);
    },
  };
}

function seed(client: QueryClient) {
  client.setQueryData(["public"], { title: "kept" }, {});
  client
    .getQueryCache()
    .build(client, { queryKey: ["opted-in"], meta: { persist: true } })
    .setData({ title: "persisted" });
  client
    .getQueryCache()
    .build(client, { queryKey: ["profile"] })
    .setData({ email: `${SENTINEL}@example.com` });
  // A paused (offline) mutation whose variables carry a credential.
  client.getMutationCache().build(
    client,
    // gcTime Infinity: no garbage-collection timer to keep Jest alive.
    { mutationKey: ["sign-in"], gcTime: Infinity },
    {
      context: undefined,
      data: undefined,
      error: null,
      failureCount: 0,
      failureReason: null,
      isPaused: true,
      status: "pending",
      variables: { email: "a@example.com", password: SENTINEL },
      submittedAt: Date.now(),
    },
  );
}

async function save(
  client: QueryClient,
  storage: ReturnType<typeof memoryStorage>,
  scope: string,
) {
  const { persistOptions } = createScopedQueryCache({
    appVersion: "1.0.0",
    scope,
    storage,
    throttleTime: 0,
  });
  await persistQueryClientSave({ queryClient: client, ...persistOptions });
  // The async-storage persister writes on a (zero-length) timer.
  await new Promise((resolve) => setTimeout(resolve, 0));
}

describe("persisted query cache (M6)", () => {
  it("writes only opted-in queries and never mutations", async () => {
    const storage = memoryStorage();
    const client = newClient();
    seed(client);
    await save(client, storage, SIGNED_OUT_SCOPE);

    const raw = storage.data.get(queryCacheStorageKey(SIGNED_OUT_SCOPE));
    expect(raw).toBeDefined();
    expect(raw).not.toContain(SENTINEL);
    const persisted = JSON.parse(raw!).clientState;
    expect(persisted.mutations).toEqual([]);
    expect(persisted.queries.map((q: { queryKey: unknown }) => q.queryKey)).toEqual([
      ["opted-in"],
    ]);
  });

  it("keeps each account's cache separate", async () => {
    const storage = memoryStorage();
    const alice = newClient();
    seed(alice);
    await save(alice, storage, "account-alice");

    const bob = newClient();
    await persistQueryClientRestore({
      queryClient: bob,
      ...createScopedQueryCache({ appVersion: "1.0.0", scope: "account-bob", storage })
        .persistOptions,
    });
    expect(bob.getQueryData(["opted-in"])).toBeUndefined();

    const aliceAgain = newClient();
    await persistQueryClientRestore({
      queryClient: aliceAgain,
      ...createScopedQueryCache({
        appVersion: "1.0.0",
        scope: "account-alice",
        storage,
      }).persistOptions,
    });
    expect(aliceAgain.getQueryData(["opted-in"])).toEqual({ title: "persisted" });
  });

  it("discards a cache written under another scope's key", async () => {
    const storage = memoryStorage();
    const alice = newClient();
    seed(alice);
    await save(alice, storage, "account-alice");
    // Simulate a mix-up: Bob's key holds Alice's cache.
    storage.data.set(
      queryCacheStorageKey("account-bob"),
      storage.data.get(queryCacheStorageKey("account-alice"))!,
    );

    const bob = newClient();
    await persistQueryClientRestore({
      queryClient: bob,
      ...createScopedQueryCache({ appVersion: "1.0.0", scope: "account-bob", storage })
        .persistOptions,
    });
    expect(bob.getQueryData(["opted-in"])).toBeUndefined();
  });

  it("clears memory and disk on sign-out", async () => {
    const storage = memoryStorage();
    const client = newClient();
    seed(client);
    await save(client, storage, "account-alice");

    const cache = createScopedQueryCache({
      appVersion: "1.0.0",
      scope: "account-alice",
      storage,
    });
    await cache.clear(client);
    expect(client.getQueryCache().getAll()).toHaveLength(0);
    expect(storage.data.has(queryCacheStorageKey("account-alice"))).toBe(false);
  });

  it("prunes other scopes' caches but leaves unrelated keys", async () => {
    const storage = memoryStorage();
    storage.data.set(queryCacheStorageKey("account-alice"), "{}");
    storage.data.set(queryCacheStorageKey("account-bob"), "{}");
    storage.data.set("settings", "{}");

    await pruneOtherQueryCaches("account-bob", storage);
    expect([...storage.data.keys()].sort()).toEqual([
      queryCacheStorageKey("account-bob"),
      "settings",
    ]);
  });
});

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

describe("retiring a scope (R2-2)", () => {
  const ALICE = queryCacheStorageKey("account-alice");

  it("sign-out with a throttled write still queued leaves nothing on disk", async () => {
    const storage = memoryStorage();
    const client = newClient();
    seed(client);
    const cache = createScopedQueryCache({
      appVersion: "1.0.0",
      scope: "account-alice",
      storage,
      throttleTime: 50,
    });
    const persist = () =>
      persistQueryClientSave({ queryClient: client, ...cache.persistOptions });

    await persist(); // first write runs at once
    await sleep(0);
    expect(storage.data.has(ALICE)).toBe(true);
    void persist(); // second write is queued for the end of the throttle window

    await cache.clear(client);
    expect(storage.data.has(ALICE)).toBe(false);

    await sleep(120); // the queued write fires now
    expect(storage.data.has(ALICE)).toBe(false);
  });

  it("waits for an in-flight write before deleting", async () => {
    const storage = memoryStorage();
    // A slow native write: the value lands only when the write completes.
    let finishWrite!: () => void;
    storage.setItem = (key: string, value: string) =>
      new Promise<void>((resolve) => {
        finishWrite = () => {
          storage.data.set(key, value);
          resolve();
        };
      });
    const client = newClient();
    seed(client);
    const cache = createScopedQueryCache({
      appVersion: "1.0.0",
      scope: "account-alice",
      storage,
      throttleTime: 0,
    });
    void persistQueryClientSave({ queryClient: client, ...cache.persistOptions });
    await sleep(0); // the write is now in flight

    const cleared = cache.clear(client);
    await sleep(0);
    finishWrite();
    await cleared;
    expect(storage.data.has(ALICE)).toBe(false);
  });

  it("pruning waits for a retiring scope, so its last write can't land afterwards", async () => {
    const storage = memoryStorage();
    let finishWrite!: () => void;
    const realSetItem = storage.setItem;
    storage.setItem = (key: string, value: string) =>
      new Promise<void>((resolve) => {
        finishWrite = () => void realSetItem(key, value).then(resolve);
      });
    const client = newClient();
    seed(client);
    const alice = createScopedQueryCache({
      appVersion: "1.0.0",
      scope: "account-alice",
      storage,
      throttleTime: 0,
    });
    void persistQueryClientSave({ queryClient: client, ...alice.persistOptions });
    await sleep(0);

    // Switching accounts: Alice's provider unmounts (retire), Bob's prunes.
    void alice.retire();
    const pruned = pruneOtherQueryCaches("account-bob", storage);
    await sleep(0);
    finishWrite();
    await pruned;
    expect(storage.data.has(ALICE)).toBe(false);
  });

  it("drops writes after retirement", async () => {
    const storage = memoryStorage();
    const client = newClient();
    seed(client);
    const cache = createScopedQueryCache({
      appVersion: "1.0.0",
      scope: "account-alice",
      storage,
      throttleTime: 0,
    });
    await cache.retire();
    await persistQueryClientSave({ queryClient: client, ...cache.persistOptions });
    await sleep(10);
    expect(storage.data.has(ALICE)).toBe(false);
  });
});

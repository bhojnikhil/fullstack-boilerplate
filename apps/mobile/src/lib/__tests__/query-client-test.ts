import { QueryClient } from "@tanstack/react-query";
import {
  persistQueryClientRestore,
  persistQueryClientSave,
} from "@tanstack/react-query-persist-client";

import {
  clearQueryCache,
  createPersistOptions,
  createQueryClient,
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
    { mutationKey: ["sign-in"] },
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
  const options = createPersistOptions({
    appVersion: "1.0.0",
    scope,
    storage,
    throttleTime: 0,
  });
  await persistQueryClientSave({ queryClient: client, ...options });
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
      ...createPersistOptions({ appVersion: "1.0.0", scope: "account-bob", storage }),
    });
    expect(bob.getQueryData(["opted-in"])).toBeUndefined();

    const aliceAgain = newClient();
    await persistQueryClientRestore({
      queryClient: aliceAgain,
      ...createPersistOptions({ appVersion: "1.0.0", scope: "account-alice", storage }),
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
      ...createPersistOptions({ appVersion: "1.0.0", scope: "account-bob", storage }),
    });
    expect(bob.getQueryData(["opted-in"])).toBeUndefined();
  });

  it("clears memory and disk on sign-out", async () => {
    const storage = memoryStorage();
    const client = newClient();
    seed(client);
    await save(client, storage, "account-alice");

    await clearQueryCache(client, "account-alice", storage);
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

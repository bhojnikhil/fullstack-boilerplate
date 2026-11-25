import {
  createMutationQueue,
  parseQueue,
  pruneOtherQueues,
  queueStorageKey,
  type QueuedMutation,
  type SendOutcome,
} from "../mutation-queue";

function memoryStorage() {
  const data = new Map<string, string>();
  return {
    data,
    getItem: async (k: string) => data.get(k) ?? null,
    setItem: async (k: string, v: string) => void data.set(k, v),
    removeItem: async (k: string) => void data.delete(k),
    getAllKeys: async () => [...data.keys()],
    multiRemove: async (keys: readonly string[]) => keys.forEach((k) => data.delete(k)),
  };
}

type Send = (m: QueuedMutation) => Promise<SendOutcome | { rejected: string }>;

function setup(send: Send, storage = memoryStorage()) {
  const queue = createMutationQueue({ accountId: "acct", send, storage });
  return { queue, storage };
}

const create = (title: string) =>
  ({
    kind: "item.create",
    workspaceId: "ws",
    body: { title, description: null },
  }) as const;

describe("mutation queue", () => {
  it("persists entries and replays them in order, each with its own idempotency key", async () => {
    const sent: QueuedMutation[] = [];
    const { queue, storage } = setup(async (m) => {
      sent.push(m);
      return "done";
    });
    await queue.enqueue(create("one"));
    await queue.enqueue(create("two"));
    expect(JSON.parse(storage.data.get(queueStorageKey("acct"))!)).toHaveLength(2);

    await queue.flush();

    expect(sent.map((m) => (m.kind === "item.create" ? m.body.title : ""))).toEqual([
      "one",
      "two",
    ]);
    expect(new Set(sent.map((m) => m.key)).size).toBe(2);
    expect(queue.entries()).toHaveLength(0);
    expect(JSON.parse(storage.data.get(queueStorageKey("acct"))!)).toEqual([]);
  });

  it("keeps an entry, with the same idempotency key, until a later attempt succeeds", async () => {
    const keys: string[] = [];
    let online = false;
    const { queue } = setup(async (m) => {
      keys.push(m.key);
      if (!online) throw new TypeError("Network request failed");
      return "done";
    });
    await queue.enqueue(create("offline write"));

    await queue.flush(); // offline: stays queued
    expect(queue.entries()).toHaveLength(1);
    online = true;
    await queue.flush(); // reconnect: replayed

    expect(queue.entries()).toHaveLength(0);
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
  });

  it("stops at an entry that must be retried and does not skip ahead", async () => {
    const sent: string[] = [];
    const { queue } = setup(async (m) => {
      sent.push(m.id);
      return "retry";
    });
    await queue.enqueue(create("a"));
    await queue.enqueue(create("b"));
    await queue.flush();
    expect(sent).toHaveLength(1);
    expect(queue.entries()).toHaveLength(2);
  });

  it("drops a rejected entry, reports it, and continues with the rest", async () => {
    const { queue } = setup(async (m) =>
      m.kind === "item.create" && m.body.title === "bad"
        ? { rejected: "too long" }
        : "done",
    );
    await queue.enqueue(create("bad"));
    await queue.enqueue(create("good"));
    await queue.flush();
    expect(queue.entries()).toHaveLength(0);
    expect(queue.failures()).toHaveLength(1);
    expect(queue.failures()[0]?.reason).toBe("too long");
  });

  it("survives a restart: a new queue reads the persisted entries", async () => {
    const storage = memoryStorage();
    const first = setup(async () => "retry", storage).queue;
    const entry = await first.enqueue(create("kept"));

    const second = setup(async () => "done", storage).queue;
    await second.load();
    expect(second.entries().map((m) => m.id)).toEqual([entry.id]);
    expect(second.entries()[0]?.key).toBe(entry.key);
  });

  it("edits a pending create in place instead of queueing a second request", async () => {
    const { queue } = setup(async () => "retry");
    const entry = await queue.enqueue(create("draft"));
    expect(await queue.patchCreate(entry.id, { title: "final" })).toBe(true);
    expect(queue.entries()).toHaveLength(1);
    expect(queue.entries()[0]).toMatchObject({ body: { title: "final" } });
  });

  it("stores plain item data only: no credentials", async () => {
    const { queue, storage } = setup(async () => "retry");
    await queue.enqueue(create("note"));
    const raw = storage.data.get(queueStorageKey("acct"))!;
    expect(raw).not.toMatch(/token|password|authorization|bearer/i);
  });

  it("clear() deletes the persisted copy and ignores later writes", async () => {
    const { queue, storage } = setup(async () => "retry");
    await queue.enqueue(create("x"));
    await queue.clear();
    await queue.enqueue(create("after")).catch(() => undefined);
    expect(storage.data.has(queueStorageKey("acct"))).toBe(false);
  });

  it("prunes other accounts' queues", async () => {
    const storage = memoryStorage();
    storage.data.set(queueStorageKey("a"), "[]");
    storage.data.set(queueStorageKey("b"), "[]");
    storage.data.set("unrelated", "x");
    await pruneOtherQueues("a", storage);
    expect([...storage.data.keys()].sort()).toEqual(
      [queueStorageKey("a"), "unrelated"].sort(),
    );
  });
});

describe("parseQueue", () => {
  it("ignores malformed or unknown entries", () => {
    const raw = JSON.stringify([
      {
        kind: "item.create",
        id: "1",
        key: "k",
        createdAt: 1,
        workspaceId: null,
        body: { title: "ok" },
      },
      {
        kind: "auth.login",
        id: "2",
        key: "k",
        createdAt: 1,
        workspaceId: null,
        body: { password: "x" },
      },
      {
        kind: "item.update",
        id: "3",
        key: "k",
        createdAt: 1,
        workspaceId: null,
        body: {},
      },
      "nope",
    ]);
    expect(parseQueue(raw).map((m) => m.id)).toEqual(["1"]);
    expect(parseQueue("{not json")).toEqual([]);
    expect(parseQueue(null)).toEqual([]);
  });
});

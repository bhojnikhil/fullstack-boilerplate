import type { QueuedMutation } from "@/lib/mutation-queue";

import { overlayQueue, type ServerItem } from "../use-items";
import { classifyStatus } from "../queue-provider";

const server: ServerItem[] = [
  {
    id: "s1",
    title: "Server one",
    description: null,
    is_active: true,
    created_at: "2026-01-01",
  },
];
const entry = (m: Partial<QueuedMutation> & Pick<QueuedMutation, "kind">) =>
  ({ id: "q1", key: "k", createdAt: 1, workspaceId: "ws", ...m }) as QueuedMutation;

describe("overlayQueue", () => {
  it("shows queued creates first, marked as waiting to sync", () => {
    const items = overlayQueue(
      server,
      [entry({ kind: "item.create", body: { title: "New", description: null } })],
      "ws",
    );
    expect(items.map((i) => i.title)).toEqual(["New", "Server one"]);
    expect(items[0]).toMatchObject({ pending: true, local: true, queueId: "q1" });
    expect(items[1]).toMatchObject({ pending: false, local: false });
  });

  it("applies queued edits to the matching server item", () => {
    const items = overlayQueue(
      server,
      [entry({ kind: "item.update", itemId: "s1", body: { title: "Edited" } })],
      "ws",
    );
    expect(items[0]).toMatchObject({ title: "Edited", pending: true });
  });

  it("ignores entries made in another workspace", () => {
    const items = overlayQueue(
      server,
      [
        entry({
          kind: "item.create",
          workspaceId: "other",
          body: { title: "X", description: null },
        }),
      ],
      "ws",
    );
    expect(items).toHaveLength(1);
  });
});

describe("classifyStatus", () => {
  it.each([
    [201, "", "done"],
    [401, "invalid_token", "retry"],
    [429, "rate_limited", "retry"],
    [503, "x", "retry"],
    [426, "app_update_required", "retry"],
    [409, "idempotency_in_progress", "retry"],
    [422, "validation_error", "rejected"],
    [404, "item_not_found", "rejected"],
    [409, "idempotency_mismatch", "rejected"],
  ])("%i %s -> %s", (status, code, outcome) => {
    expect(classifyStatus(status, code)).toBe(outcome);
  });
});

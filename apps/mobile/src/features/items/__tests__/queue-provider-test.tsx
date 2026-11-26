import { act, render, waitFor } from "@testing-library/react-native";
import { onlineManager, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { QueueProvider, useMutationQueue } from "../queue-provider";
import { ServicesProvider } from "@/providers/services";
import type { MutationQueue } from "@/lib/mutation-queue";
import { makeServices, json } from "../../../../test-utils/services";
import { makeAccessToken } from "../../../../test-utils/fake-api";

it("retires an in-flight account queue before another account can send its next write", async () => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const { services, requests } = makeServices({
    "POST /v1/items": async () => {
      await gate;
      return json(201, { id: "item-1" });
    },
  });
  await services.session.load();
  services.workspaceId.set("other-workspace");
  onlineManager.setOnline(false);
  let queue!: MutationQueue;
  function Child() {
    queue = useMutationQueue();
    return null;
  }
  const client = new QueryClient();
  const view = await render(
    <ServicesProvider services={services}>
      <QueryClientProvider client={client}>
        <QueueProvider>
          <Child />
        </QueueProvider>
      </QueryClientProvider>
    </ServicesProvider>,
  );
  await act(async () => {
    await queue.enqueue({
      kind: "item.create",
      workspaceId: "original-workspace",
      body: { title: "one", description: null },
    });
    await queue.enqueue({
      kind: "item.create",
      workspaceId: "original-workspace",
      body: { title: "two", description: null },
    });
    onlineManager.setOnline(true);
  });
  await waitFor(() => expect(requests).toHaveLength(1));
  expect(requests[0]?.headers.get("X-Workspace-Id")).toBe("original-workspace");
  await act(async () => {
    await services.session.signIn({
      accessToken: makeAccessToken("sid-B", "user-B"),
      refreshToken: "refresh-B",
    });
    release();
  });
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(requests).toHaveLength(1);
  expect(requests[0]?.headers.get("Authorization")).toContain(
    makeAccessToken("sid-1", "user-1"),
  );
  await view.unmount();
  onlineManager.setOnline(true);
});

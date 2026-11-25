import { createApiClient, type components } from "@repo/api-client";

test("imports the generated API client in Expo", () => {
  const client = createApiClient({ baseUrl: "https://example.test" });
  const user: components["schemas"]["UserResponse"] | null = null;
  expect(client.GET).toBeDefined();
  expect(user).toBeNull();
});

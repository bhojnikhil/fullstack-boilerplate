import { routeFromNotificationData } from "../push";

describe("routeFromNotificationData", () => {
  const id = "123e4567-e89b-12d3-a456-426614174000";
  it.each([
    [{ url: "/items" }, "/items"],
    [{ url: `/item/${id}` }, `/item/${id}`],
    [{ url: "/workspaces" }, "/workspaces"],
  ])("follows allowed in-app routes %j", (data, route) => {
    expect(routeFromNotificationData(data)).toBe(route);
  });

  it.each([
    [{ url: "https://evil.example/x" }],
    [{ url: "//evil.example" }],
    [{ url: "/delete-account" }],
    [{ url: "/item/../delete-account" }],
    [{ url: "boilerplate://delete-account" }],
    [{ url: 5 }],
    [null],
    [undefined],
  ])("ignores %j", (data) => {
    expect(routeFromNotificationData(data)).toBeNull();
  });
});

/** @vitest-environment jsdom */
import axios, {
  AxiosError,
  type AxiosAdapter,
  type InternalAxiosRequestConfig,
} from "axios";
import { afterEach, expect, it } from "vitest";
import { ApiClient } from "@/lib/api";

const originalAdapter = axios.defaults.adapter;
afterEach(() => {
  axios.defaults.adapter = originalAdapter;
  localStorage.clear();
});

function tokens(user: string, sid: string) {
  return {
    access_token: `x.${btoa(JSON.stringify({ sid }))}.x`,
    csrf_token: "csrf",
    expires_in: 900,
    user: { id: user, name: user, email: `${user}@example.com`, email_verified: true },
  };
}
function ok(config: InternalAxiosRequestConfig, data: unknown) {
  return { config, data, status: 200, statusText: "OK", headers: {} };
}
function unauthorized(config: InternalAxiosRequestConfig): never {
  throw new AxiosError("unauthorized", "401", config, undefined, {
    ...ok(config, {}),
    status: 401,
  });
}

it("does not retry a write when a different tab replaced the session", async () => {
  let writes = 0;
  axios.defaults.adapter = (async (config) => {
    if (config.url === "/v1/auth/login") return ok(config, tokens("a", "one"));
    if (config.url === "/v1/auth/refresh") return ok(config, tokens("b", "two"));
    writes++;
    return unauthorized(config);
  }) satisfies AxiosAdapter;
  const api = new ApiClient();
  await api.login("a@example.com", "password");
  await expect(api.createItem("write", "")).rejects.toThrow("different session");
  expect(writes).toBe(1);
});

it("refreshes an expired access token before revoking the same session", async () => {
  let logoutCalls = 0;
  let revoked = false;
  axios.defaults.adapter = (async (config) => {
    if (config.url === "/v1/auth/login") return ok(config, tokens("a", "one"));
    if (config.url === "/v1/auth/refresh") {
      if (revoked) return unauthorized(config);
      return ok(config, tokens("a", "one"));
    }
    if (config.url === "/v1/auth/logout") {
      if (++logoutCalls === 1) return unauthorized(config);
      revoked = true;
      return ok(config, {});
    }
    throw new Error("unexpected request");
  }) satisfies AxiosAdapter;
  const api = new ApiClient();
  await api.login("a@example.com", "password");
  await api.logout();
  expect(logoutCalls).toBe(2);
  expect(await api.refresh()).toBeNull();
});

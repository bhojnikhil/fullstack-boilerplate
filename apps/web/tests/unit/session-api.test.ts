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

it("preserves the refresh credential after a transient error", async () => {
  let attempts = 0;
  axios.defaults.adapter = (async (config) => {
    if (config.url === "/v1/auth/login") return ok(config, tokens("a", "one"));
    if (++attempts === 1)
      throw new AxiosError("network failure", "ERR_NETWORK", config);
    return ok(config, tokens("a", "one"));
  }) satisfies AxiosAdapter;
  const api = new ApiClient();
  await api.login("a@example.com", "password");
  await expect(api.refresh()).rejects.toThrow("network failure");
  expect(localStorage.getItem("csrf_token")).toBe("csrf");
  expect((await api.refresh())?.user.id).toBe("a");
});

it("surfaces logout failure and permits retry", async () => {
  let calls = 0;
  axios.defaults.adapter = (async (config) => {
    if (config.url === "/v1/auth/login") return ok(config, tokens("a", "one"));
    if (config.url === "/v1/auth/logout") {
      if (++calls === 1) throw new AxiosError("network failure", "ERR_NETWORK", config);
      return ok(config, {});
    }
    throw new Error("unexpected request");
  }) satisfies AxiosAdapter;
  const api = new ApiClient();
  await api.login("a@example.com", "password");
  await expect(api.logout()).rejects.toThrow("network failure");
  expect(localStorage.getItem("csrf_token")).toBe("csrf");
  await api.logout();
  expect(calls).toBe(2);
});

it("does not clear another tab's CSRF value when logging out", async () => {
  axios.defaults.adapter = (async (config) => {
    if (config.url === "/v1/auth/login") return ok(config, tokens("a", "one"));
    return ok(config, {});
  }) satisfies AxiosAdapter;
  const api = new ApiClient();
  await api.login("a@example.com", "password");
  localStorage.setItem("csrf_token", "other-session-csrf");
  await api.logout();
  expect(localStorage.getItem("csrf_token")).toBe("other-session-csrf");
});

it("reports an unconfirmable logout when no token or CSRF value remains", async () => {
  axios.defaults.adapter = (async (config) => {
    if (config.url === "/v1/auth/login") return ok(config, tokens("a", "one"));
    return unauthorized(config);
  }) satisfies AxiosAdapter;
  const api = new ApiClient();
  await api.login("a@example.com", "password");
  await api.refresh();
  await expect(api.logout()).rejects.toThrow("Could not confirm sign out");
});

it("clears the matching CSRF value when refresh is rejected", async () => {
  axios.defaults.adapter = (async (config) => {
    if (config.url === "/v1/auth/login") return ok(config, tokens("a", "one"));
    return unauthorized(config);
  }) satisfies AxiosAdapter;
  const api = new ApiClient();
  await api.login("a@example.com", "password");
  expect(await api.refresh()).toBeNull();
  expect(localStorage.getItem("csrf_token")).toBeNull();
});

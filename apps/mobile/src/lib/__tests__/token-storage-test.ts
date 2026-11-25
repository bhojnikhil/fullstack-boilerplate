import * as SecureStore from "expo-secure-store";

import {
  createTokenStorage,
  SECURE_STORE_OPTIONS,
  SESSION_KEY,
  type SecureStoreLike,
} from "../token-storage";

function fakeSecureStore() {
  const data = new Map<string, string>();
  const store = {
    data,
    getItemAsync: jest.fn(async (key: string) => data.get(key) ?? null),
    setItemAsync: jest.fn(async (key: string, value: string) => {
      data.set(key, value);
    }),
    deleteItemAsync: jest.fn(async (key: string) => {
      data.delete(key);
    }),
  } satisfies SecureStoreLike & { data: Map<string, string> };
  return store;
}

const TOKENS = { accessToken: "access.jwt", refreshToken: "opaque-refresh" };
const NEW_TOKENS = { accessToken: "access.jwt.2", refreshToken: "opaque-refresh-2" };

describe("token storage", () => {
  it("returns null when nothing is stored", async () => {
    const storage = createTokenStorage(fakeSecureStore());
    await expect(storage.getTokens()).resolves.toBeNull();
  });

  it("round-trips tokens", async () => {
    const storage = createTokenStorage(fakeSecureStore());
    await storage.setTokens(TOKENS);
    await expect(storage.getTokens()).resolves.toEqual(TOKENS);
  });

  it("stores the whole session in one entry with device-only keychain access", async () => {
    const store = fakeSecureStore();
    await createTokenStorage(store).setTokens(TOKENS);
    expect(store.setItemAsync).toHaveBeenCalledTimes(1);
    expect(store.setItemAsync).toHaveBeenCalledWith(
      SESSION_KEY,
      expect.any(String),
      SECURE_STORE_OPTIONS,
    );
    expect([...store.data.keys()]).toEqual([SESSION_KEY]);
    expect(SECURE_STORE_OPTIONS.keychainAccessible).toBe(
      SecureStore.AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY,
    );
  });

  it("uses a key that expo-secure-store accepts", () => {
    expect(SESSION_KEY).toMatch(/^[\w.-]+$/);
  });

  it("keeps the previous pair intact when replacing it fails (M5)", async () => {
    const store = fakeSecureStore();
    const storage = createTokenStorage(store);
    await storage.setTokens(TOKENS);

    store.setItemAsync.mockRejectedValueOnce(new Error("keystore unavailable"));
    await expect(storage.setTokens(NEW_TOKENS)).rejects.toThrow("keystore unavailable");

    // Never a mix of old and new tokens.
    await expect(storage.getTokens()).resolves.toEqual(TOKENS);
  });

  it("replaces both tokens together", async () => {
    const storage = createTokenStorage(fakeSecureStore());
    await storage.setTokens(TOKENS);
    await storage.setTokens(NEW_TOKENS);
    await expect(storage.getTokens()).resolves.toEqual(NEW_TOKENS);
  });

  it("clears the session", async () => {
    const store = fakeSecureStore();
    const storage = createTokenStorage(store);
    await storage.setTokens(TOKENS);
    await storage.clearTokens();
    expect(store.data.size).toBe(0);
    await expect(storage.getTokens()).resolves.toBeNull();
  });

  it.each([
    "not json",
    "null",
    JSON.stringify({ accessToken: "a", refreshToken: "r" }),
    JSON.stringify({ v: 1, accessToken: "a" }),
    JSON.stringify({ v: 1, accessToken: "", refreshToken: "r" }),
    JSON.stringify({ v: 2, accessToken: "a", refreshToken: "r" }),
  ])("treats an unreadable entry as signed out and removes it: %s", async (raw) => {
    const store = fakeSecureStore();
    store.data.set(SESSION_KEY, raw);
    await expect(createTokenStorage(store).getTokens()).resolves.toBeNull();
    expect(store.data.size).toBe(0);
  });

  it.each([
    { accessToken: "", refreshToken: "r" },
    { accessToken: "a", refreshToken: "" },
  ])("rejects empty tokens without writing: %o", async (tokens) => {
    const store = fakeSecureStore();
    await expect(createTokenStorage(store).setTokens(tokens)).rejects.toThrow(
      TypeError,
    );
    expect(store.setItemAsync).not.toHaveBeenCalled();
  });

  it("propagates secure store read failures", async () => {
    const store = fakeSecureStore();
    store.getItemAsync.mockRejectedValueOnce(new Error("keystore unavailable"));
    await expect(createTokenStorage(store).getTokens()).rejects.toThrow(
      "keystore unavailable",
    );
  });
});

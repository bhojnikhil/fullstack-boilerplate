import * as SecureStore from "expo-secure-store";

import {
  createTokenStorage,
  SECURE_STORE_OPTIONS,
  TOKEN_KEYS,
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

  it("stores each token under its own key with device-only keychain access", async () => {
    const store = fakeSecureStore();
    await createTokenStorage(store).setTokens(TOKENS);
    expect(store.setItemAsync).toHaveBeenCalledWith(
      TOKEN_KEYS.accessToken,
      TOKENS.accessToken,
      SECURE_STORE_OPTIONS,
    );
    expect(store.setItemAsync).toHaveBeenCalledWith(
      TOKEN_KEYS.refreshToken,
      TOKENS.refreshToken,
      SECURE_STORE_OPTIONS,
    );
    expect(SECURE_STORE_OPTIONS.keychainAccessible).toBe(
      SecureStore.AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY,
    );
  });

  it("uses keys that expo-secure-store accepts", () => {
    for (const key of Object.values(TOKEN_KEYS)) {
      expect(key).toMatch(/^[\w.-]+$/);
    }
  });

  it("clears both tokens", async () => {
    const store = fakeSecureStore();
    const storage = createTokenStorage(store);
    await storage.setTokens(TOKENS);
    await storage.clearTokens();
    expect(store.data.size).toBe(0);
    await expect(storage.getTokens()).resolves.toBeNull();
  });

  it("treats a half-written pair as signed out and removes it", async () => {
    const store = fakeSecureStore();
    store.data.set(TOKEN_KEYS.refreshToken, "orphaned");
    const storage = createTokenStorage(store);
    await expect(storage.getTokens()).resolves.toBeNull();
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

  it("propagates secure store failures", async () => {
    const store = fakeSecureStore();
    store.getItemAsync.mockRejectedValueOnce(new Error("keystore unavailable"));
    await expect(createTokenStorage(store).getTokens()).rejects.toThrow(
      "keystore unavailable",
    );
  });
});

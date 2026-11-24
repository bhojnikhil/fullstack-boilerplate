import * as SecureStore from "expo-secure-store";

/**
 * Typed wrapper over expo-secure-store (iOS Keychain / Android Keystore) for
 * auth tokens. Interface only for now: nothing reads or writes tokens until
 * the auth flows land (phase 9b).
 */
export interface AuthTokens {
  accessToken: string;
  refreshToken: string;
}

export interface TokenStorage {
  /** Both tokens, or null if none (or only one, which is treated as none). */
  getTokens(): Promise<AuthTokens | null>;
  setTokens(tokens: AuthTokens): Promise<void>;
  clearTokens(): Promise<void>;
}

/** The subset of expo-secure-store used here; injectable for tests. */
export interface SecureStoreLike {
  getItemAsync(
    key: string,
    options?: SecureStore.SecureStoreOptions,
  ): Promise<string | null>;
  setItemAsync(
    key: string,
    value: string,
    options?: SecureStore.SecureStoreOptions,
  ): Promise<void>;
  deleteItemAsync(key: string, options?: SecureStore.SecureStoreOptions): Promise<void>;
}

// Separate entries keep each value small (Android has historically warned on
// values over 2 KB) and avoid JSON parsing of secrets.
export const TOKEN_KEYS = {
  accessToken: "auth.accessToken",
  refreshToken: "auth.refreshToken",
} as const;

/**
 * Readable after the first unlock (so background work such as notification
 * handling can refresh a session) and never migrated to another device via
 * backups.
 */
export const SECURE_STORE_OPTIONS: SecureStore.SecureStoreOptions = {
  keychainAccessible: SecureStore.AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY,
};

function assertToken(name: keyof AuthTokens, value: unknown): asserts value is string {
  if (typeof value !== "string" || value.length === 0) {
    throw new TypeError(`${name} must be a non-empty string`);
  }
}

export function createTokenStorage(store: SecureStoreLike = SecureStore): TokenStorage {
  async function clearTokens(): Promise<void> {
    await Promise.all([
      store.deleteItemAsync(TOKEN_KEYS.accessToken, SECURE_STORE_OPTIONS),
      store.deleteItemAsync(TOKEN_KEYS.refreshToken, SECURE_STORE_OPTIONS),
    ]);
  }

  return {
    async getTokens() {
      const [accessToken, refreshToken] = await Promise.all([
        store.getItemAsync(TOKEN_KEYS.accessToken, SECURE_STORE_OPTIONS),
        store.getItemAsync(TOKEN_KEYS.refreshToken, SECURE_STORE_OPTIONS),
      ]);
      if (accessToken && refreshToken) return { accessToken, refreshToken };
      // A half-written pair (e.g. the app was killed mid-write) is unusable.
      if (accessToken || refreshToken) await clearTokens();
      return null;
    },

    async setTokens(tokens) {
      assertToken("accessToken", tokens.accessToken);
      assertToken("refreshToken", tokens.refreshToken);
      await store.setItemAsync(
        TOKEN_KEYS.refreshToken,
        tokens.refreshToken,
        SECURE_STORE_OPTIONS,
      );
      await store.setItemAsync(
        TOKEN_KEYS.accessToken,
        tokens.accessToken,
        SECURE_STORE_OPTIONS,
      );
    },

    clearTokens,
  };
}

export const tokenStorage: TokenStorage = createTokenStorage();

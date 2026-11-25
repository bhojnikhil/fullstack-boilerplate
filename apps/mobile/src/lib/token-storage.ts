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
  /** Both tokens, or null if there is no (readable) session. */
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

/**
 * One SecureStore entry holds the whole session, so a write either replaces
 * both tokens or neither: there is no state where an old access token is
 * paired with a new refresh token.
 */
export const SESSION_KEY = "auth.session";

/**
 * Readable after the first unlock (so background work such as notification
 * handling can refresh a session) and never migrated to another device via
 * backups.
 */
export const SECURE_STORE_OPTIONS: SecureStore.SecureStoreOptions = {
  keychainAccessible: SecureStore.AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY,
};

interface StoredSession extends AuthTokens {
  v: 1;
}

function assertToken(name: keyof AuthTokens, value: unknown): asserts value is string {
  if (typeof value !== "string" || value.length === 0) {
    throw new TypeError(`${name} must be a non-empty string`);
  }
}

function parseSession(raw: string): AuthTokens | null {
  try {
    const data: unknown = JSON.parse(raw);
    if (typeof data !== "object" || data === null) return null;
    const { v, accessToken, refreshToken } = data as Partial<StoredSession>;
    if (v !== 1) return null;
    if (typeof accessToken !== "string" || accessToken.length === 0) return null;
    if (typeof refreshToken !== "string" || refreshToken.length === 0) return null;
    return { accessToken, refreshToken };
  } catch {
    return null;
  }
}

export function createTokenStorage(store: SecureStoreLike = SecureStore): TokenStorage {
  async function clearTokens(): Promise<void> {
    await store.deleteItemAsync(SESSION_KEY, SECURE_STORE_OPTIONS);
  }

  return {
    async getTokens() {
      const raw = await store.getItemAsync(SESSION_KEY, SECURE_STORE_OPTIONS);
      if (raw === null) return null;
      const tokens = parseSession(raw);
      // Unreadable data (corrupt or from an unknown format) is unusable.
      if (!tokens) await clearTokens();
      return tokens;
    },

    async setTokens(tokens) {
      assertToken("accessToken", tokens.accessToken);
      assertToken("refreshToken", tokens.refreshToken);
      const record: StoredSession = {
        v: 1,
        accessToken: tokens.accessToken,
        refreshToken: tokens.refreshToken,
      };
      await store.setItemAsync(
        SESSION_KEY,
        JSON.stringify(record),
        SECURE_STORE_OPTIONS,
      );
    },

    clearTokens,
  };
}

export const tokenStorage: TokenStorage = createTokenStorage();

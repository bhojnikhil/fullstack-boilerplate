import { isAxiosError } from "axios";
import { create } from "zustand";
import { api, type User } from "./api";

interface ErrorEnvelope {
  error?: { message?: unknown; details?: { fields?: { location?: unknown[] }[] } };
}

// Mirrors the API's limits for new passwords (see the OpenAPI schema).
const PASSWORD_HINT = "Use a password of 12 to 128 characters.";

/** The API's error message from an axios error, if it has one. */
function errorDetail(error: unknown, fallback: string): string {
  if (isAxiosError<ErrorEnvelope>(error)) {
    const body = error.response?.data?.error;
    const fields = body?.details?.fields ?? [];
    if (fields.some((field) => field.location?.at(-1) === "password"))
      return PASSWORD_HINT;
    if (typeof body?.message === "string") return body.message;
  }
  return fallback;
}

interface AuthStore {
  user: User | null;
  isLoading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, name: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  /** After a page load: use the refresh cookie, if any, to sign back in. */
  restoreSession: () => Promise<boolean>;
}

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  isLoading: false,
  error: null,

  login: async (email: string, password: string) => {
    set({ isLoading: true, error: null });
    try {
      const { user } = await api.login(email, password);
      set({ user, isLoading: false });
    } catch (error) {
      set({
        error: errorDetail(error, "Login failed"),
        isLoading: false,
      });
      throw error;
    }
  },

  register: async (email: string, name: string, password: string) => {
    set({ isLoading: true, error: null });
    try {
      await api.register(email, name, password);
      set({ isLoading: false });
    } catch (error) {
      set({ error: errorDetail(error, "Registration failed"), isLoading: false });
      throw error;
    }
  },

  logout: async () => {
    try {
      await api.logout();
    } finally {
      set({ user: null });
    }
  },

  restoreSession: async () => {
    const session = await api.refresh();
    set({ user: session?.user ?? null });
    return session !== null;
  },
}));

if (typeof window !== "undefined") {
  window.addEventListener("auth-session-changed", () => {
    useAuthStore.setState({ user: null });
    window.location.href = "/auth/login";
  });
}

import { isAxiosError } from "axios";
import { create } from "zustand";
import { api } from "./api";

/** The API's `detail` message from an axios error, if it has one. */
function errorDetail(error: unknown, fallback: string): string {
  if (isAxiosError<{ detail?: unknown }>(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") return detail;
  }
  return fallback;
}

interface User {
  id: string;
  email: string;
  name: string;
}

interface AuthStore {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, name: string, password: string) => Promise<void>;
  logout: () => void;
  getCurrentUser: () => Promise<void>;
}

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  token: typeof window !== "undefined" ? localStorage.getItem("token") : null,
  isLoading: false,
  error: null,

  login: async (email: string, password: string) => {
    set({ isLoading: true, error: null });
    try {
      const response = await api.login(email, password);
      const token = response.data.access_token;
      localStorage.setItem("token", token);
      set({ token, isLoading: false });
      await useAuthStore.getState().getCurrentUser();
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
      const response = await api.register(email, name, password);
      const token = response.data.access_token;
      localStorage.setItem("token", token);
      set({ token, isLoading: false });
      await useAuthStore.getState().getCurrentUser();
    } catch (error) {
      set({
        error: errorDetail(error, "Registration failed"),
        isLoading: false,
      });
      throw error;
    }
  },

  logout: () => {
    localStorage.removeItem("token");
    set({ user: null, token: null });
  },

  getCurrentUser: async () => {
    try {
      const response = await api.getCurrentUser();
      set({ user: response.data });
    } catch {
      set({ user: null, token: null });
    }
  },
}));

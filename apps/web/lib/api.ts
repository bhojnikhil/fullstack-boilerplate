import axios, { AxiosInstance } from "axios";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface Item {
  id: string;
  title: string;
  description: string | null;
  created_at: string;
}

interface ItemPage {
  items: Item[];
  next_cursor: string | null;
}

class ApiClient {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: API_URL,
      headers: {
        "Content-Type": "application/json",
      },
    });

    // Add token to requests
    this.client.interceptors.request.use((config) => {
      const token =
        typeof window !== "undefined" ? localStorage.getItem("token") : null;
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    });

    // Handle 401 responses
    this.client.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response?.status === 401 && error.config?.url !== "/v1/auth/login") {
          if (typeof window !== "undefined") {
            localStorage.removeItem("token");
            window.location.href = "/auth/login";
          }
        }
        return Promise.reject(error);
      },
    );
  }

  // Auth endpoints
  register(email: string, name: string, password: string) {
    return this.client.post("/v1/auth/register", { email, name, password });
  }

  login(email: string, password: string) {
    return this.client.post("/v1/auth/login", { email, password });
  }

  getCurrentUser() {
    return this.client.get("/v1/auth/me");
  }

  // Items endpoints
  getItems(cursor?: string) {
    return this.client.get<ItemPage>("/v1/items", { params: { cursor } });
  }

  getItem(id: string) {
    return this.client.get(`/v1/items/${id}`);
  }

  createItem(title: string, description: string) {
    return this.client.post("/v1/items", { title, description });
  }

  updateItem(id: string, title: string, description: string) {
    return this.client.patch(`/v1/items/${id}`, { title, description });
  }

  deleteItem(id: string) {
    return this.client.delete(`/v1/items/${id}`);
  }

  // Health check
  health() {
    return this.client.get("/health");
  }
}

export const api = new ApiClient();

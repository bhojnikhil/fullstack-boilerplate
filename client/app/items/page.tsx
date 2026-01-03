"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/auth-store";
import { api } from "@/lib/api";

interface Item {
  id: string;
  title: string;
  description: string;
  created_at: string;
}

export default function ItemsPage() {
  const router = useRouter();
  const { user } = useAuthStore();
  const [items, setItems] = useState<Item[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!user) {
      router.push("/auth/login");
      return;
    }

    loadItems();
  }, [user, router]);

  const loadItems = async () => {
    try {
      setIsLoading(true);
      const response = await api.getItems();
      setItems(response.data);
      setError("");
    } catch (err: any) {
      setError("Failed to load items");
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCreateItem = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setError("Title is required");
      return;
    }

    try {
      await api.createItem(title, description);
      setTitle("");
      setDescription("");
      setError("");
      await loadItems();
    } catch (err: any) {
      setError("Failed to create item");
      console.error(err);
    }
  };

  const handleDeleteItem = async (id: string) => {
    try {
      await api.deleteItem(id);
      await loadItems();
    } catch (err: any) {
      setError("Failed to delete item");
      console.error(err);
    }
  };

  if (!user) {
    return null;
  }

  return (
    <>
      <header className="header">
        <div className="container">
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <h1>Items</h1>
            <div>
              <span style={{ marginRight: "1rem" }}>Welcome, {user.name}</span>
              <button
                className="button button-secondary"
                onClick={() => {
                  useAuthStore.getState().logout();
                  router.push("/");
                }}
              >
                Logout
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="main">
        <div className="container">
          <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: "2rem" }}>
            <div className="card">
              <h2>Create Item</h2>
              <form onSubmit={handleCreateItem} style={{ marginTop: "1rem" }}>
                <div style={{ marginBottom: "1rem" }}>
                  <label htmlFor="title">Title</label>
                  <input
                    id="title"
                    type="text"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    style={{ width: "100%", marginTop: "0.5rem" }}
                  />
                </div>

                <div style={{ marginBottom: "1rem" }}>
                  <label htmlFor="description">Description</label>
                  <textarea
                    id="description"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    style={{
                      width: "100%",
                      marginTop: "0.5rem",
                      minHeight: "100px",
                      border: "1px solid #d1d5db",
                      borderRadius: "0.375rem",
                      padding: "0.5rem",
                    }}
                  />
                </div>

                <button type="submit" className="button" style={{ width: "100%" }}>
                  Create
                </button>
              </form>
            </div>

            <div>
              {error && (
                <div className="card" style={{ marginBottom: "1rem", background: "#fee2e2" }}>
                  <span className="error">{error}</span>
                </div>
              )}

              {isLoading ? (
                <div className="card">Loading items...</div>
              ) : items.length === 0 ? (
                <div className="card">No items yet. Create one to get started!</div>
              ) : (
                <div style={{ display: "grid", gap: "1rem" }}>
                  {items.map((item) => (
                    <div key={item.id} className="card">
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "start",
                        }}
                      >
                        <div>
                          <h3>{item.title}</h3>
                          <p>{item.description}</p>
                          <small style={{ color: "#6b7280" }}>
                            {new Date(item.created_at).toLocaleDateString()}
                          </small>
                        </div>
                        <button
                          className="button button-secondary"
                          onClick={() => handleDeleteItem(item.id)}
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </>
  );
}

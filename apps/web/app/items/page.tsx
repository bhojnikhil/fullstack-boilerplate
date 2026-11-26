"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/auth-store";
import {
  api,
  ApiError,
  getActiveWorkspace,
  setActiveWorkspace,
  type Item,
} from "@/lib/api";
import { FormError, TextField } from "@/components/form";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";

export default function ItemsPage() {
  const router = useRouter();
  const { user, restoreSession } = useAuthStore();
  const [workspace, setWorkspace] = useState<{ id: string; name: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const intent = useRef<{ signature: string; key: string } | null>(null);
  const workspaceRef = useRef<string | null>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [failureCount, setFailureCount] = useState(0);

  const loadItems = async (workspaceId: string, cursor?: string) => {
    const setLoading = cursor ? setIsLoadingMore : setIsLoading;
    try {
      setLoading(true);
      const { data } = await api.getItems(workspaceId, cursor);
      if (workspaceRef.current !== workspaceId) return;
      setItems((previous) => (cursor ? [...previous, ...data.items] : data.items));
      setNextCursor(data.next_cursor);
      setError("");
    } catch (err) {
      if (workspaceRef.current !== workspaceId) return;
      if (err instanceof ApiError && err.status === 404) {
        setActiveWorkspace(null);
        setWorkspace(null);
        router.replace("/workspaces");
      } else setError("Failed to load items");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!user) {
      // The access token is kept in memory only; after a reload, try the refresh cookie.
      void restoreSession()
        .then((restored) => {
          if (!restored) router.push("/auth/login");
        })
        .catch(() => {
          setError("Could not restore your session. Reload to try again.");
        });
      return;
    }

    const workspaceId = getActiveWorkspace();
    if (!workspaceId) {
      router.replace("/workspaces");
      return;
    }
    let active = true;
    workspaceRef.current = workspaceId;
    void api
      .workspace(workspaceId)
      .then((w) => {
        if (!active) return;
        setWorkspace({ id: w.id, name: w.name });
        void loadItems(workspaceId);
      })
      .catch((err) => {
        if (!active) return;
        if (err instanceof ApiError && err.status === 404) {
          setActiveWorkspace(null);
          router.replace("/workspaces");
        } else setError("Could not load the active workspace.");
      });
    const onStorage = (event: StorageEvent) => {
      if (event.key?.startsWith("workspace:") && getActiveWorkspace() !== workspaceId) {
        active = false;
        workspaceRef.current = null;
        setWorkspace(null);
        setItems([]);
        setTitle("");
        setDescription("");
        setEditingId(null);
        intent.current = null;
        router.replace("/workspaces");
      }
    };
    window.addEventListener("storage", onStorage);
    return () => {
      active = false;
      workspaceRef.current = null;
      window.removeEventListener("storage", onStorage);
    };
    // loadItems uses the workspace id captured by this effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, router, restoreSession]);

  const handleCreateItem = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setError("Title is required");
      setFailureCount((count) => count + 1);
      return;
    }

    if (!workspace || savingRef.current) return;
    const signature = JSON.stringify([workspace.id, editingId, title, description]);
    if (intent.current?.signature !== signature)
      intent.current = { signature, key: crypto.randomUUID() };
    const key = intent.current.key;
    savingRef.current = true;
    setSaving(true);
    try {
      if (editingId)
        await api.updateItem(workspace.id, editingId, title, description, key);
      else await api.createItem(workspace.id, title, description, key);
      if (workspaceRef.current !== workspace.id) return;
      intent.current = null;
      setEditingId(null);
      setTitle("");
      setDescription("");
      setError("");
      await loadItems(workspace.id);
    } catch (err) {
      setError("Failed to save item");
      setFailureCount((count) => count + 1);
      console.error(err);
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  };

  const handleDeleteItem = async (id: string) => {
    try {
      if (!workspace || savingRef.current) return;
      savingRef.current = true;
      setSaving(true);
      await api.deleteItem(workspace.id, id, crypto.randomUUID());
      await loadItems(workspace.id);
    } catch (err) {
      setError("Failed to delete item");
      console.error(err);
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  };

  if (!user) {
    return error ? <p role="alert">{error}</p> : null;
  }

  return (
    <>
      <p className="mb-4">Workspace: {workspace?.name}</p>
      <div className="mb-8 flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-3xl font-semibold tracking-tight">Items</h1>
        <div className="flex flex-wrap items-center gap-4">
          <span>Welcome, {user.name}</span>
          <Button
            variant="secondary"
            onClick={async () => {
              try {
                await useAuthStore.getState().logout();
                router.push("/");
              } catch {
                setError("Could not sign out. Please try again.");
                setFailureCount((count) => count + 1);
              }
            }}
          >
            Logout
          </Button>
        </div>
      </div>

      <div className="grid items-start gap-6 md:grid-cols-[1fr_2fr]">
        <div className="rounded-xl border bg-card p-5">
          <h2 className="text-xl font-semibold">
            {editingId ? "Edit item" : "Create item"}
          </h2>
          <form onSubmit={handleCreateItem} className="mt-4 grid gap-4">
            <TextField
              label="Title"
              id="title"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
            <div className="grid gap-2">
              <Label htmlFor="description">Description</Label>
              <textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="min-h-24 w-full rounded-md border border-input bg-transparent px-3 py-2 text-base shadow-xs transition-[color,box-shadow] outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring md:text-sm dark:bg-input/30"
              />
            </div>
            <Button type="submit" disabled={isLoadingMore || saving || !workspace}>
              {editingId ? "Save changes" : "Create"}
            </Button>
            {editingId && (
              <Button
                type="button"
                variant="secondary"
                onClick={() => {
                  setEditingId(null);
                  setTitle("");
                  setDescription("");
                }}
              >
                Cancel edit
              </Button>
            )}
          </form>
        </div>

        <div className="grid gap-4">
          <FormError message={error} failureCount={failureCount} />
          {isLoading ? (
            <div className="rounded-xl border bg-card p-5">Loading items...</div>
          ) : items.length === 0 ? (
            <div className="rounded-xl border bg-card p-5">
              No items yet. Create one to get started!
            </div>
          ) : (
            <>
              {items.map((item) => (
                <div key={item.id} className="rounded-xl border bg-card p-5">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 wrap-break-word">
                      <h3 className="font-semibold">{item.title}</h3>
                      <p>{item.description}</p>
                      <small className="text-muted-foreground">
                        {new Date(item.created_at).toLocaleDateString()}
                      </small>
                    </div>
                    <Button
                      variant="secondary"
                      onClick={() => {
                        setEditingId(item.id);
                        setTitle(item.title);
                        setDescription(item.description ?? "");
                      }}
                    >
                      Edit {item.title}
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() => handleDeleteItem(item.id)}
                      disabled={isLoadingMore || saving || !workspace}
                    >
                      Delete {item.title}
                    </Button>
                  </div>
                </div>
              ))}
              {nextCursor && (
                <Button
                  type="button"
                  variant="secondary"
                  disabled={isLoadingMore || saving || !workspace}
                  onClick={() => workspace && loadItems(workspace.id, nextCursor)}
                >
                  {isLoadingMore ? "Loading…" : "Load more"}
                </Button>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}

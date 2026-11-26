"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import { FormError, TextField } from "@/components/form";
import { Button } from "@/components/ui/button";
import type { components } from "@repo/api-client";

type Session = components["schemas"]["SessionResponse"];
export default function AccountPage() {
  const router = useRouter();
  const { user, restoreSession } = useAuthStore();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [sessions, setSessions] = useState<Session[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [failures, setFailures] = useState(0);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!user) {
      void restoreSession()
        .then((ok) => {
          if (!ok) router.push("/auth/login");
        })
        .catch(() => setError("Could not restore your session."));
      return;
    }
    // Load account details and the first session page after authentication.
    void api
      .sessions()
      .then((page) => {
        setSessions(page.items);
        setCursor(page.next_cursor);
      })
      .catch(() => setError("Could not load sessions."));
  }, [user, restoreSession, router]);
  async function run(action: () => Promise<void>, success: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      setNotice(success);
    } catch {
      setError("The request failed. Check your details and try again.");
      setFailures((n) => n + 1);
    } finally {
      setBusy(false);
    }
  }
  if (!user) return error ? <p role="alert">{error}</p> : null;
  return (
    <div className="mx-auto grid max-w-xl gap-8">
      <h1 className="text-3xl font-semibold">Account</h1>
      <FormError message={error} failureCount={failures} />
      {notice && <p role="status">{notice}</p>}
      <form
        className="grid gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          void run(async () => {
            const updated = await api.updateProfile(name);
            useAuthStore.setState({ user: updated });
          }, "Profile updated.");
        }}
      >
        <h2 className="text-xl font-semibold">Profile</h2>
        <p>
          Current name: {user.name} · {user.email}
        </p>
        <TextField
          label="New name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <Button disabled={busy}>Save profile</Button>
      </form>
      <form
        className="grid gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          void run(async () => {
            await api.changePassword(password, newPassword);
            setPassword("");
            setNewPassword("");
          }, "Password changed; other sessions were signed out.");
        }}
      >
        <h2 className="text-xl font-semibold">Change password</h2>
        <TextField
          label="Current password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <TextField
          label="New password"
          type="password"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          required
        />
        <Button disabled={busy}>Change password</Button>
      </form>
      <form
        className="grid gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          void run(async () => {
            await api.reauthenticate(password);
            await api.changeEmail(email);
          }, "Check your new email address for a confirmation link.");
        }}
      >
        <h2 className="text-xl font-semibold">Change email</h2>
        <TextField
          label="New email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <TextField
          label="Password to confirm identity"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <Button disabled={busy}>Request email change</Button>
      </form>
      <section className="grid gap-3">
        <h2 className="text-xl font-semibold">Sessions</h2>
        {sessions.map((s) => (
          <div key={s.id} className="flex justify-between gap-2">
            <span>
              {s.device_name || "Unknown device"}
              {s.current ? " (current)" : ""} —{" "}
              {new Date(s.last_used_at).toLocaleString()}
            </span>
            {!s.current && (
              <Button
                disabled={busy}
                variant="secondary"
                onClick={() =>
                  void run(async () => {
                    await api.revokeSession(s.id);
                    setSessions((v) => v.filter((item) => item.id !== s.id));
                  }, "Session revoked.")
                }
              >
                Revoke
              </Button>
            )}
          </div>
        ))}
        {cursor && (
          <Button
            disabled={busy}
            variant="secondary"
            onClick={() =>
              void run(async () => {
                const page = await api.sessions(cursor);
                setSessions((v) => [...v, ...page.items]);
                setCursor(page.next_cursor);
              }, "Sessions loaded.")
            }
          >
            Load more sessions
          </Button>
        )}
        <Button
          disabled={busy}
          variant="secondary"
          onClick={() =>
            void run(async () => {
              await api.revokeOtherSessions();
              setSessions((v) => v.filter((s) => s.current));
              setCursor(null);
            }, "Other sessions revoked.")
          }
        >
          Sign out other sessions
        </Button>
      </section>
      <form
        className="grid gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (!window.confirm("Permanently delete your account?")) return;
          void run(async () => {
            await api.reauthenticate(password);
            await api.deleteAccount();
            useAuthStore.setState({ user: null });
            router.push("/");
          }, "Account deleted.");
        }}
      >
        <h2 className="text-xl font-semibold">Delete account</h2>
        <p>This permanently deletes your account.</p>
        <TextField
          label="Password to delete account"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <Button disabled={busy} variant="destructive">
          Delete account
        </Button>
      </form>
    </div>
  );
}

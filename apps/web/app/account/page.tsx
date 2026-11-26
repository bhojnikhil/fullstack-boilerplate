"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import { GoogleReauthenticate } from "@/components/google-reauthenticate";
import { FormError, TextField } from "@/components/form";
import { Button } from "@/components/ui/button";
import type { components } from "@repo/api-client";
type Session = components["schemas"]["SessionResponse"];
type Section = "profile" | "password" | "email" | "sessions" | "delete" | "session";
export default function AccountPage() {
  const router = useRouter();
  const { user, restoreSession } = useAuthStore();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [emailPassword, setEmailPassword] = useState("");
  const [deletePassword, setDeletePassword] = useState("");
  const [verified, setVerified] = useState(false);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState<{
    section: Section;
    message: string;
    blocked?: boolean;
  } | null>(null);
  const [notice, setNotice] = useState("");
  const [failures, setFailures] = useState(0);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!user) {
      void restoreSession()
        .then((ok) => {
          if (!ok) router.push("/auth/login");
        })
        .catch(() =>
          setError({ section: "session", message: "Could not restore your session." }),
        );
      return;
    }
    void api
      .sessions()
      .then((page) => {
        setSessions(page.items);
        setCursor(page.next_cursor);
      })
      .catch(() =>
        setError({ section: "sessions", message: "Could not load sessions." }),
      );
  }, [user, restoreSession, router]);
  async function run(section: Section, action: () => Promise<void>, success: string) {
    setBusy(true);
    setError(null);
    setNotice("");
    try {
      await action();
      setNotice(success);
    } catch (cause) {
      const envelope =
        cause instanceof ApiError
          ? (
              cause.body as
                | { error?: { message?: unknown; code?: string; details?: unknown } }
                | undefined
            )?.error
          : undefined;
      const details = envelope?.details as { reason?: unknown } | undefined;
      setError({
        section,
        message:
          typeof envelope?.message === "string"
            ? envelope.message
            : "The request failed. Check your details and try again.",
        blocked:
          envelope?.code === "account_deletion_blocked" &&
          details?.reason === "sole_workspace_owner",
      });
      setFailures((n) => n + 1);
    } finally {
      setBusy(false);
    }
  }
  function sectionError(section: Section) {
    return (
      <>
        <FormError
          message={error?.section === section ? error.message : ""}
          failureCount={failures}
        />
        {error?.section === section && error.blocked && (
          <p>
            Transfer ownership or remove other members in{" "}
            <Link href="/workspaces" className="underline">
              Workspaces
            </Link>{" "}
            before deleting your account.
          </p>
        )}
      </>
    );
  }
  if (!user) return error ? <p role="alert">{error.message}</p> : null;
  const hasPassword = user.sign_in_methods.includes("password");
  async function confirmIdentity(password: string) {
    if (hasPassword) await api.reauthenticate({ password });
    else if (!verified) throw new Error("Verify with Google first.");
  }
  return (
    <div className="mx-auto grid max-w-xl gap-8">
      <h1 className="text-3xl font-semibold">Account</h1>
      {notice && <p role="status">{notice}</p>}
      {!hasPassword && (
        <section>
          <GoogleReauthenticate onVerified={() => setVerified(true)} />
          {verified && <p role="status">Identity verified.</p>}
          <p>
            You can also{" "}
            <Link className="underline" href="/auth/forgot-password">
              recover your password
            </Link>{" "}
            to set one.
          </p>
        </section>
      )}
      <form
        className="grid gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          void run(
            "profile",
            async () => {
              const updated = await api.updateProfile(name);
              useAuthStore.setState({ user: updated });
            },
            "Profile updated.",
          );
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
        {sectionError("profile")}
        <Button disabled={busy}>Save profile</Button>
      </form>
      {hasPassword && (
        <form
          className="grid gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            void run(
              "password",
              async () => {
                try {
                  await api.changePassword(currentPassword, newPassword);
                } finally {
                  setCurrentPassword("");
                  setNewPassword("");
                }
              },
              "Password changed; other sessions were signed out.",
            );
          }}
        >
          <h2 className="text-xl font-semibold">Change password</h2>
          <TextField
            label="Current password"
            type="password"
            autoComplete="current-password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            required
          />
          <TextField
            label="New password"
            type="password"
            autoComplete="new-password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
          />
          {sectionError("password")}
          <Button disabled={busy}>Change password</Button>
        </form>
      )}
      <form
        className="grid gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          void run(
            "email",
            async () => {
              try {
                await confirmIdentity(emailPassword);
                await api.changeEmail(email);
                setVerified(false);
              } finally {
                setEmailPassword("");
              }
            },
            "Check your new email address for a confirmation link.",
          );
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
        {hasPassword && (
          <TextField
            label="Password to confirm identity"
            type="password"
            autoComplete="current-password"
            value={emailPassword}
            onChange={(e) => setEmailPassword(e.target.value)}
            required
          />
        )}
        {sectionError("email")}
        <Button disabled={busy || (!hasPassword && !verified)}>
          Request email change
        </Button>
      </form>
      <section className="grid gap-3">
        <h2 className="text-xl font-semibold">Sessions</h2>
        {sectionError("sessions")}
        {sessions.map((s) => (
          <div key={s.id} className="flex justify-between gap-2">
            <span>
              {s.device_name || "Unknown device"}
              {s.current ? " (current)" : ""} —{" "}
              {new Date(s.last_used_at).toLocaleString()}
            </span>
            {!s.current && (
              <Button
                aria-label={`Revoke session ${s.device_name || s.id}`}
                disabled={busy}
                variant="secondary"
                onClick={() =>
                  void run(
                    "sessions",
                    async () => {
                      await api.revokeSession(s.id);
                      setSessions((v) => v.filter((item) => item.id !== s.id));
                    },
                    "Session revoked.",
                  )
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
              void run(
                "sessions",
                async () => {
                  const page = await api.sessions(cursor);
                  setSessions((v) => [...v, ...page.items]);
                  setCursor(page.next_cursor);
                },
                "Sessions loaded.",
              )
            }
          >
            Load more sessions
          </Button>
        )}
        <Button
          disabled={busy}
          variant="secondary"
          onClick={() =>
            void run(
              "sessions",
              async () => {
                await api.revokeOtherSessions();
                setSessions((v) => v.filter((s) => s.current));
                setCursor(null);
              },
              "Other sessions revoked.",
            )
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
          void run(
            "delete",
            async () => {
              try {
                await confirmIdentity(deletePassword);
                await api.deleteAccount();
                setVerified(false);
                useAuthStore.setState({ user: null });
                router.push("/");
              } finally {
                setDeletePassword("");
              }
            },
            "Account deleted.",
          );
        }}
      >
        <h2 className="text-xl font-semibold">Delete account</h2>
        <p>This permanently deletes your account.</p>
        {hasPassword && (
          <TextField
            label="Password to delete account"
            type="password"
            autoComplete="current-password"
            value={deletePassword}
            onChange={(e) => setDeletePassword(e.target.value)}
            required
          />
        )}
        {sectionError("delete")}
        <Button disabled={busy || (!hasPassword && !verified)} variant="destructive">
          Delete account
        </Button>
      </form>
    </div>
  );
}

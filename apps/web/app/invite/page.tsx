"use client";
import { useState } from "react";
import Link from "next/link";
import { api, setActiveWorkspace } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import { FormError } from "@/components/form";
import { Button } from "@/components/ui/button";
export default function InvitePage() {
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  async function accept() {
    const token = new URLSearchParams(window.location.hash.slice(1)).get("token");
    if (!token) {
      setError("This invitation link is missing its token.");
      return;
    }
    setBusy(true);
    try {
      const session =
        useAuthStore.getState().user ||
        (await useAuthStore.getState().restoreSession());
      if (!session) {
        setError("Sign in first, then reopen this invitation link.");
        return;
      }
      const workspace = await api.acceptInvitation(token);
      setActiveWorkspace(workspace.id);
      window.history.replaceState(null, "", window.location.pathname);
      setDone(true);
    } catch {
      setError("Could not accept this invitation. It may be expired or invalid.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="mx-auto grid max-w-md gap-4">
      <h1 className="text-3xl font-semibold">Workspace invitation</h1>
      {done ? (
        <p>
          Invitation accepted.{" "}
          <Link href="/workspaces" className="underline">
            Open workspaces
          </Link>
          .
        </p>
      ) : (
        <>
          <p>Sign in with the invited email address before accepting.</p>
          <FormError message={error} />
          <Button disabled={busy} onClick={() => void accept()}>
            Accept invitation
          </Button>
          <Link href="/auth/login" className="underline">
            Sign in
          </Link>
        </>
      )}
    </section>
  );
}

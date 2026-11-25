"use client";

import { useState } from "react";
import Link from "next/link";
import { FormError, TextField } from "@/components/form";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

export default function VerifyEmailPage() {
  const [password, setPassword] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  const [failures, setFailures] = useState(0);
  const [loading, setLoading] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const token = new URLSearchParams(window.location.hash.slice(1)).get("token");
    if (!token) {
      setError("This verification link is missing its token.");
      setFailures((count) => count + 1);
      return;
    }
    setLoading(true);
    try {
      await api.verifyEmail(token, password);
      window.history.replaceState(null, "", window.location.pathname);
      setDone(true);
    } catch {
      setError("Verification failed. Check your password or request a new link.");
      setFailures((count) => count + 1);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="mx-auto max-w-md rounded-xl border bg-card p-6 sm:p-8">
      <h1 className="text-3xl font-semibold tracking-tight">Verify email</h1>
      {done ? (
        <p className="mt-6">
          Your email is verified. <Link href="/auth/login">Sign in</Link>.
        </p>
      ) : (
        <form onSubmit={submit} className="mt-6 grid gap-4">
          <p>Enter the password you chose when registering.</p>
          <TextField
            label="Password"
            id="password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
          <FormError message={error} failureCount={failures} />
          <Button type="submit" disabled={loading}>
            Verify email
          </Button>
        </form>
      )}
    </section>
  );
}

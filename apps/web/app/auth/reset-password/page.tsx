"use client";

import { useState } from "react";
import Link from "next/link";
import { FormError, TextField } from "@/components/form";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

export default function ResetPasswordPage() {
  const [password, setPassword] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  const [failures, setFailures] = useState(0);
  const [loading, setLoading] = useState(false);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const token = new URLSearchParams(window.location.hash.slice(1)).get("token");
    if (!token) {
      setError("This reset link is missing its token.");
      setFailures((n) => n + 1);
      return;
    }
    setLoading(true);
    setError("");
    try {
      await api.resetPassword(token, password);
      window.history.replaceState(null, "", window.location.pathname);
      setDone(true);
    } catch {
      setError("Could not reset your password. Check the link and try again.");
      setFailures((n) => n + 1);
    } finally {
      setLoading(false);
    }
  }
  return (
    <section className="mx-auto max-w-md rounded-xl border bg-card p-6 sm:p-8">
      <h1 className="text-3xl font-semibold tracking-tight">Reset password</h1>
      {done ? (
        <p className="mt-6">
          Your password has been reset.{" "}
          <Link href="/auth/login" className="underline">
            Sign in
          </Link>
          .
        </p>
      ) : (
        <form onSubmit={submit} className="mt-6 grid gap-4">
          <TextField
            label="New password"
            type="password"
            autoComplete="new-password"
            minLength={12}
            maxLength={128}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
          <FormError message={error} failureCount={failures} />
          <Button disabled={loading}>Reset password</Button>
        </form>
      )}
    </section>
  );
}

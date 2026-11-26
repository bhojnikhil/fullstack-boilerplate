"use client";

import { useState } from "react";
import Link from "next/link";
import { FormError, TextField } from "@/components/form";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  const [failures, setFailures] = useState(0);
  const [loading, setLoading] = useState(false);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      await api.forgotPassword(email);
      setDone(true);
    } catch {
      setError("Could not request a reset link. Please try again.");
      setFailures((count) => count + 1);
    } finally {
      setLoading(false);
    }
  }
  return (
    <section className="mx-auto max-w-md rounded-xl border bg-card p-6 sm:p-8">
      <h1 className="text-3xl font-semibold tracking-tight">Forgot password</h1>
      {done ? (
        <p className="mt-6">
          If an account exists for that address, a reset link will be sent.
        </p>
      ) : (
        <form onSubmit={submit} className="mt-6 grid gap-4">
          <TextField
            label="Email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
          <FormError message={error} failureCount={failures} />
          <Button disabled={loading}>Send reset link</Button>
        </form>
      )}
      <p className="mt-4">
        <Link className="underline" href="/auth/login">
          Back to sign in
        </Link>
      </p>
    </section>
  );
}

"use client";

import { useState } from "react";
import Link from "next/link";
import { FormError } from "@/components/form";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

export default function ConfirmEmailPage() {
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  const [failures, setFailures] = useState(0);
  const [loading, setLoading] = useState(false);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const token = new URLSearchParams(window.location.hash.slice(1)).get("token");
    if (!token) {
      setError("This confirmation link is missing its token.");
      setFailures((n) => n + 1);
      return;
    }
    setLoading(true);
    setError("");
    try {
      await api.confirmEmail(token);
      window.history.replaceState(null, "", window.location.pathname);
      setDone(true);
    } catch {
      setError("Could not confirm your email. The link may have expired.");
      setFailures((n) => n + 1);
    } finally {
      setLoading(false);
    }
  }
  return (
    <section className="mx-auto max-w-md rounded-xl border bg-card p-6 sm:p-8">
      <h1 className="text-3xl font-semibold tracking-tight">Confirm email change</h1>
      {done ? (
        <p className="mt-6">
          Your email has been changed.{" "}
          <Link className="underline" href="/auth/login">
            Sign in
          </Link>
          .
        </p>
      ) : (
        <form onSubmit={submit} className="mt-6 grid gap-4">
          <p>Confirm that you want to use this email address.</p>
          <FormError message={error} failureCount={failures} />
          <Button disabled={loading}>Confirm email</Button>
        </form>
      )}
    </section>
  );
}

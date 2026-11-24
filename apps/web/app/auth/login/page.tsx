"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { FormError, TextField } from "@/components/form";
import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/lib/auth-store";

export default function LoginPage() {
  const router = useRouter();
  const { login, isLoading, error } = useAuthStore();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [formError, setFormError] = useState("");
  const [failureCount, setFailureCount] = useState(0);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError("");

    try {
      await login(email, password);
      router.push("/items");
    } catch {
      setFormError("Login failed. Please try again.");
      setFailureCount((count) => count + 1);
    }
  };

  return (
    <section className="mx-auto max-w-md rounded-xl border bg-card p-6 sm:p-8">
      <h1 className="text-3xl font-semibold tracking-tight">Login</h1>

      <form onSubmit={handleSubmit} className="mt-6 grid gap-4">
        <TextField
          label="Email"
          id="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />

        <TextField
          label="Password"
          id="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />

        <FormError message={error || formError} failureCount={failureCount} />

        <Button type="submit" disabled={isLoading} className="w-full">
          {isLoading ? "Logging in..." : "Login"}
        </Button>
      </form>

      <p className="mt-4 text-center text-sm">
        Don&apos;t have an account?{" "}
        <Link
          href="/auth/register"
          className="font-medium text-primary underline underline-offset-4"
        >
          Register here
        </Link>
      </p>
    </section>
  );
}

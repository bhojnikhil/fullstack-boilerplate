"use client";

import { useState } from "react";
import { GoogleSignIn } from "@/components/google-sign-in";
import Link from "next/link";
import { FormError, TextField } from "@/components/form";
import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/lib/auth-store";

export default function RegisterPage() {
  const { register, isLoading, error } = useAuthStore();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [formError, setFormError] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [failureCount, setFailureCount] = useState(0);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError("");

    if (password !== confirmPassword) {
      setFormError("Passwords do not match");
      setFailureCount((count) => count + 1);
      return;
    }

    try {
      await register(email, name, password);
      setSubmitted(true);
    } catch {
      setFormError("Registration failed. Please try again.");
      setFailureCount((count) => count + 1);
    }
  };

  return (
    <section className="mx-auto max-w-md rounded-xl border bg-card p-6 sm:p-8">
      <h1 className="text-3xl font-semibold tracking-tight">Register</h1>

      {submitted ? (
        <p className="mt-6">
          Check your email to continue. If you already have an account, sign in or reset
          your password.
        </p>
      ) : (
        <form onSubmit={handleSubmit} className="mt-6 grid gap-4">
          <TextField
            label="Name"
            id="name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />

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

          <TextField
            label="Confirm Password"
            id="confirm-password"
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
          />

          <FormError message={error || formError} failureCount={failureCount} />

          <Button type="submit" disabled={isLoading} className="w-full">
            {isLoading ? "Registering..." : "Register"}
          </Button>
        </form>
      )}

      <GoogleSignIn />
      <p className="mt-4 text-center text-sm">
        Already have an account?{" "}
        <Link
          href="/auth/login"
          className="font-medium text-primary underline underline-offset-4"
        >
          Login here
        </Link>
      </p>
    </section>
  );
}

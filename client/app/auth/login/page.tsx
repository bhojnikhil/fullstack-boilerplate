"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuthStore } from "@/lib/auth-store";

export default function LoginPage() {
  const router = useRouter();
  const { login, isLoading, error } = useAuthStore();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [formError, setFormError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError("");

    try {
      await login(email, password);
      router.push("/items");
    } catch (err) {
      setFormError("Login failed. Please try again.");
    }
  };

  return (
    <div className="container">
      <div className="card" style={{ maxWidth: "400px", margin: "2rem auto" }}>
        <h1>Login</h1>

        <form onSubmit={handleSubmit} style={{ marginTop: "1.5rem" }}>
          <div style={{ marginBottom: "1rem" }}>
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              style={{ width: "100%", marginTop: "0.5rem" }}
            />
          </div>

          <div style={{ marginBottom: "1rem" }}>
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              style={{ width: "100%", marginTop: "0.5rem" }}
            />
          </div>

          {(error || formError) && (
            <div className="error" style={{ marginBottom: "1rem" }}>
              {error || formError}
            </div>
          )}

          <button
            type="submit"
            disabled={isLoading}
            className="button"
            style={{ width: "100%" }}
          >
            {isLoading ? "Logging in..." : "Login"}
          </button>
        </form>

        <p style={{ marginTop: "1rem", textAlign: "center" }}>
          Don&apos;t have an account?{" "}
          <Link href="/auth/register">Register here</Link>
        </p>
      </div>
    </div>
  );
}

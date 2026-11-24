"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuthStore } from "@/lib/auth-store";

export default function RegisterPage() {
  const router = useRouter();
  const { register, isLoading, error } = useAuthStore();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [formError, setFormError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError("");

    if (password !== confirmPassword) {
      setFormError("Passwords do not match");
      return;
    }

    try {
      await register(email, name, password);
      router.push("/items");
    } catch (err) {
      setFormError("Registration failed. Please try again.");
    }
  };

  return (
    <div className="container">
      <div className="card" style={{ maxWidth: "400px", margin: "2rem auto" }}>
        <h1>Register</h1>

        <form onSubmit={handleSubmit} style={{ marginTop: "1.5rem" }}>
          <div style={{ marginBottom: "1rem" }}>
            <label htmlFor="name">Name</label>
            <input
              id="name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              style={{ width: "100%", marginTop: "0.5rem" }}
            />
          </div>

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

          <div style={{ marginBottom: "1rem" }}>
            <label htmlFor="confirm-password">Confirm Password</label>
            <input
              id="confirm-password"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
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
            {isLoading ? "Registering..." : "Register"}
          </button>
        </form>

        <p style={{ marginTop: "1rem", textAlign: "center" }}>
          Already have an account?{" "}
          <Link href="/auth/login">Login here</Link>
        </p>
      </div>
    </div>
  );
}

"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/auth-store";
import { FormError } from "@/components/form";
export function AccountNavigation() {
  const { user, restoreSession, logout } = useAuthStore();
  const router = useRouter();
  const [error, setError] = useState("");
  useEffect(() => {
    if (!user)
      void restoreSession().catch(() => setError("Could not restore your session."));
  }, [user, restoreSession]);
  return (
    <>
      {user ? (
        <>
          <span>Signed in as {user.name}</span>
          <button
            className="underline"
            onClick={() =>
              void logout()
                .then(() => router.push("/"))
                .catch(() => setError("Could not sign out."))
            }
          >
            Sign out
          </button>
        </>
      ) : (
        <Link href="/auth/login" className="hover:underline">
          Sign in
        </Link>
      )}
      <FormError message={error} />
    </>
  );
}

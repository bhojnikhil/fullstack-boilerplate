"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import { FormError } from "@/components/form";

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (options: {
            client_id: string;
            callback: (result: { credential: string }) => void;
          }) => void;
          renderButton: (
            element: HTMLElement,
            options: { theme: string; size: string },
          ) => void;
        };
      };
    };
  }
}

const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
export function GoogleSignIn() {
  const button = useRef<HTMLDivElement>(null);
  const router = useRouter();
  const [error, setError] = useState("");
  useEffect(() => {
    if (!clientId) return;
    let active = true;
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.onload = () => {
      if (!active || !window.google || !button.current) return;
      window.google.accounts.id.initialize({
        client_id: clientId,
        callback: ({ credential }) => {
          void api
            .googleLogin(credential)
            .then(({ user }) => {
              if (active) {
                useAuthStore.setState({ user });
                router.push("/items");
              }
            })
            .catch(() => {
              if (active) setError("Google sign-in failed. Please try again.");
            });
        },
      });
      window.google.accounts.id.renderButton(button.current, {
        theme: "outline",
        size: "large",
      });
    };
    script.onerror = () => {
      if (active) setError("Google sign-in could not be loaded.");
    };
    document.head.appendChild(script);
    return () => {
      active = false;
      script.remove();
    };
  }, [router]);
  if (!clientId) return null;
  return (
    <div className="mt-6 grid gap-2">
      <div ref={button} />
      <FormError message={error} />
    </div>
  );
}

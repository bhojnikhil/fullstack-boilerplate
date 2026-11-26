"use client";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { FormError } from "@/components/form";
import "@/components/google-sign-in";

export function GoogleReauthenticate({ onVerified }: { onVerified: () => void }) {
  const button = useRef<HTMLDivElement>(null);
  const verified = useRef(onVerified);
  useEffect(() => {
    verified.current = onVerified;
  }, [onVerified]);
  const [error, setError] = useState("");
  useEffect(() => {
    const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
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
            .reauthenticate({ id_token: credential })
            .then(() => {
              if (active) {
                setError("");
                verified.current();
              }
            })
            .catch(() => {
              if (active) setError("Google verification failed. Try again.");
            });
        },
      });
      window.google.accounts.id.renderButton(button.current, {
        theme: "outline",
        size: "large",
      });
    };
    script.onerror = () => {
      if (active) setError("Google verification could not be loaded.");
    };
    document.head.appendChild(script);
    return () => {
      active = false;
      script.remove();
    };
  }, []);
  return (
    <div className="grid gap-2">
      <p>Verify your identity with Google before continuing.</p>
      {process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID ? (
        <div ref={button} />
      ) : (
        <p>
          Google sign-in is not configured. Use password recovery to set a password.
        </p>
      )}
      <FormError message={error} />
    </div>
  );
}

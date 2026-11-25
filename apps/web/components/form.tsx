"use client";

import type { ComponentProps } from "react";
import { useId } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type TextFieldProps = ComponentProps<"input"> & {
  label: string;
  error?: string;
};

export function TextField({
  label,
  id,
  error,
  "aria-describedby": describedBy,
  ...props
}: TextFieldProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const errorId = error ? `${inputId}-error` : undefined;

  return (
    <div className="grid gap-2">
      <Label htmlFor={inputId}>{label}</Label>
      <Input
        {...props}
        id={inputId}
        aria-invalid={error ? true : props["aria-invalid"]}
        aria-describedby={[describedBy, errorId].filter(Boolean).join(" ") || undefined}
      />
      {error && (
        <p id={errorId} className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}

export function FormError({
  message,
  failureCount = 0,
}: {
  message?: string | null;
  failureCount?: number;
}) {
  return (
    <div role="alert" aria-atomic="true" className="empty:sr-only">
      {message && (
        <p className="rounded-md border border-destructive/40 p-3 text-sm text-destructive">
          <span key={failureCount}>{message}</span>
        </p>
      )}
    </div>
  );
}

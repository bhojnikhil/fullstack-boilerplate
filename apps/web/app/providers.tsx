"use client";

import { ThemeProvider } from "next-themes";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      // The SSR script runs before hydration. A client remount needs only the
      // provider effects, so render an inert data block in that environment.
      scriptProps={
        typeof window === "undefined" ? undefined : { type: "application/json" }
      }
    >
      {children}
    </ThemeProvider>
  );
}

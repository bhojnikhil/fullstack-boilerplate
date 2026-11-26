import type { Metadata } from "next";
import Link from "next/link";
import { appName } from "@/lib/public-settings";
import { ThemeToggle } from "@/components/theme-toggle";
import { Providers } from "./providers";
import "./globals.css";

// Render the shell and metadata with the running server’s app name.
export const dynamic = "force-dynamic";

export function generateMetadata(): Metadata {
  const name = appName();
  return {
    title: { default: name, template: `%s | ${name}` },
    description: `${name} includes user accounts and an example items page.`,
  };
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <Providers>
          <a
            href="#main-content"
            className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-10 focus:rounded-md focus:bg-card focus:px-3 focus:py-2"
          >
            Skip to content
          </a>
          <div className="flex min-h-dvh flex-col">
            <header className="border-b bg-card">
              <div className="mx-auto flex min-h-16 w-full max-w-6xl flex-wrap items-center justify-between gap-x-6 gap-y-3 px-5 py-3 sm:px-8">
                <Link href="/" className="text-lg font-bold tracking-tight">
                  {appName()}
                </Link>
                <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
                  <nav aria-label="Main navigation" className="flex gap-4 text-sm">
                    <Link href="/workspaces" className="hover:underline">
                      Workspaces
                    </Link>
                    <Link href="/account" className="hover:underline">
                      Account
                    </Link>
                    <Link href="/items" className="hover:underline">
                      Items
                    </Link>
                    <Link href="/auth/login" className="hover:underline">
                      Sign in
                    </Link>
                  </nav>
                  <ThemeToggle />
                </div>
              </div>
            </header>
            <main
              id="main-content"
              tabIndex={-1}
              className="mx-auto w-full max-w-6xl flex-1 px-5 py-12 sm:px-8 sm:py-16"
            >
              {children}
            </main>
            <footer className="border-t bg-card">
              <nav
                aria-label="Policies and support"
                className="mx-auto flex max-w-6xl flex-wrap gap-x-6 gap-y-2 px-5 py-5 text-sm text-muted-foreground sm:px-8"
              >
                <Link href="/privacy" className="hover:underline">
                  Privacy
                </Link>
                <Link href="/terms" className="hover:underline">
                  Terms
                </Link>
                <Link href="/account-deletion" className="hover:underline">
                  Account deletion
                </Link>
              </nav>
            </footer>
          </div>
        </Providers>
      </body>
    </html>
  );
}

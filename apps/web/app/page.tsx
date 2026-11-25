import Link from "next/link";
import { Button } from "@/components/ui/button";
import { appName } from "@/lib/public-settings";

export default function Home() {
  return (
    <section className="relative overflow-hidden rounded-2xl border bg-card px-6 py-14 sm:px-14 sm:py-20">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-y-0 right-0 hidden w-2/5 bg-[linear-gradient(var(--border)_1px,transparent_1px),linear-gradient(90deg,var(--border)_1px,transparent_1px)] bg-size-[24px_24px] mask-l-from-10% sm:block"
      />
      <div className="relative max-w-2xl">
        <h1 className="text-4xl leading-tight font-semibold tracking-tight sm:text-6xl">
          {appName()}
        </h1>
        <p className="mt-5 max-w-md text-lg leading-relaxed text-muted-foreground">
          A Next.js and FastAPI starter with user accounts and an example items page.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Button asChild size="lg">
            <Link href="/auth/register">Create an account</Link>
          </Button>
          <Button asChild size="lg" variant="outline">
            <Link href="/items">Open items</Link>
          </Button>
        </div>
      </div>
    </section>
  );
}

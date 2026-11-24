import type { ReactNode } from "react";

export function PublicDocument({
  title,
  template = false,
  children,
}: {
  title: string;
  template?: boolean;
  children: ReactNode;
}) {
  return (
    <article className="mx-auto max-w-2xl rounded-xl border bg-card p-6 sm:p-10">
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{title}</h1>
      {template && (
        <p className="mt-5 rounded-md border border-input bg-secondary p-4 text-sm text-secondary-foreground">
          <strong>Template.</strong> Complete and review this page before publishing.
        </p>
      )}
      <div className="mt-6 space-y-6 leading-relaxed [&_h2]:mb-2 [&_h2]:text-lg [&_h2]:font-semibold [&_p+p]:mt-3">
        {children}
      </div>
    </article>
  );
}

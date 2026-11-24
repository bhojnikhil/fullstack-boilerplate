import type { Metadata } from "next";
import { PublicDocument } from "@/components/public-document";
import { supportEmail } from "@/lib/public-settings";

export const metadata: Metadata = { title: "Account deletion" };
export const dynamic = "force-dynamic";

export default function AccountDeletionPage() {
  const email = supportEmail();

  return (
    <PublicDocument title="Account deletion">
      <section>
        <h2>Delete your account in the app</h2>
        <p>
          If your version of the app has account deletion, sign in, open Settings,
          select Account, and choose Delete account. Follow the confirmation steps shown
          in the app.
        </p>
      </section>
      <section>
        <h2>Request deletion without the app</h2>
        {email ? (
          <p>
            Email{" "}
            <a
              href={`mailto:${email}?subject=Account%20deletion%20request`}
              className="font-medium break-all text-primary underline underline-offset-4"
            >
              {email}
            </a>{" "}
            from the address associated with your account. Ask us to delete your
            account. Keep your password and verification codes private.
          </p>
        ) : (
          <p>A support email has yet to be configured for this installation.</p>
        )}
      </section>
    </PublicDocument>
  );
}

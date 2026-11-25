import type { Metadata } from "next";
import { PublicDocument } from "@/components/public-document";
import { legalDetails, supportEmail } from "@/lib/public-settings";

export const metadata: Metadata = { title: "Account deletion" };
export const dynamic = "force-dynamic";

export default function AccountDeletionPage() {
  const { appName } = legalDetails();
  const email = supportEmail();

  return (
    <PublicDocument title="Account deletion" template>
      <p>How to request deletion of your {appName} account and associated data.</p>
      <section>
        <h2>Delete your account in the app</h2>
        <p>
          [Add the in-app steps for starting account deletion and describe how users
          confirm the request.]
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
          <p className="rounded-md border border-destructive/40 p-3 text-destructive">
            <strong>Deletion requests are unavailable.</strong> A support email has yet
            to be configured for this installation.
          </p>
        )}
      </section>
      <section>
        <h2>Data deleted or retained</h2>
        <ul>
          <li>
            [List the account and associated data deleted when a request is completed.]
          </li>
          <li>
            [List any data retained, why it is retained, and the retention period.]
          </li>
        </ul>
      </section>
    </PublicDocument>
  );
}

import type { Metadata } from "next";
import Link from "next/link";
import { PublicDocument } from "@/components/public-document";
import { legalDetails } from "@/lib/public-settings";

export const metadata: Metadata = { title: "Privacy policy" };
export const dynamic = "force-dynamic";

export default function PrivacyPage() {
  const { appName, domain } = legalDetails();

  return (
    <PublicDocument title="Privacy policy" template>
      <p>
        [Legal operator] operates {appName} at {domain}. Effective [effective date].
      </p>
      <section>
        <h2>Data we collect and why</h2>
        <p>[Describe the data collected, the sources, and the purpose of each use.]</p>
      </section>
      <section>
        <h2>Sharing and retention</h2>
        <p>[Identify recipients and explain how long each kind of data is kept.]</p>
      </section>
      <section>
        <h2>Your choices and rights</h2>
        <p>[Describe applicable rights and give a privacy contact address.]</p>
        <p>
          See{" "}
          <Link
            href="/account-deletion"
            className="font-medium text-primary underline underline-offset-4"
          >
            account deletion
          </Link>{" "}
          for deletion request instructions.
        </p>
      </section>
    </PublicDocument>
  );
}

import type { Metadata } from "next";
import { PublicDocument } from "@/components/public-document";
import { legalDetails } from "@/lib/public-settings";

export const metadata: Metadata = { title: "Terms of service" };
export const dynamic = "force-dynamic";

export default function TermsPage() {
  const { appName, domain } = legalDetails();

  return (
    <PublicDocument title="Terms of service" template>
      <p>
        [Legal operator] provides {appName} at {domain}. Effective [effective date].
      </p>
      <section>
        <h2>Using the service</h2>
        <p>[Describe eligibility, acceptable use, and account responsibilities.]</p>
      </section>
      <section>
        <h2>Changes and termination</h2>
        <p>[Explain billing if applicable, service changes, and how access ends.]</p>
      </section>
      <section>
        <h2>Governing law and contact</h2>
        <p>[Specify jurisdiction, dispute terms, and a contact address.]</p>
      </section>
    </PublicDocument>
  );
}

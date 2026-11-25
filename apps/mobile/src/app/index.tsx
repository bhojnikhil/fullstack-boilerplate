import { Redirect } from "expo-router";

import { peekPendingInvite } from "@/features/workspaces/pending-invite";
import { useSession } from "@/providers/services";

/** Entry point: sends the user to the signed-in app (or a pending invite) or to sign-in. */
export default function Index() {
  const { status } = useSession();
  if (status !== "signedIn") return <Redirect href="/sign-in" />;
  const invite = peekPendingInvite();
  if (invite)
    return (
      <Redirect href={{ pathname: "/invite/[token]", params: { token: invite } }} />
    );
  return <Redirect href="/items" />;
}

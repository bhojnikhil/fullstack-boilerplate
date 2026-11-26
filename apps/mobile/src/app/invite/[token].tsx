import { useQueryClient } from "@tanstack/react-query";
import { router, useLocalSearchParams } from "expo-router";

import { Button } from "@/components/button";
import { Screen } from "@/components/screen";
import { Body, ErrorText, Title } from "@/components/ui";
import { useSubmit } from "@/features/auth/use-submit";
import {
  clearPendingInvite,
  setPendingInvite,
} from "@/features/workspaces/pending-invite";
import { useWorkspaceClient } from "@/features/workspaces/use-workspaces";
import { ApiError, describeError } from "@/lib/api-error";
import { useServices, useSession } from "@/providers/services";
import { useTheme } from "@/theme/use-theme";

/** Deep link target of an invitation (…/invite/<token>). */
export default function AcceptInvite() {
  const { token } = useLocalSearchParams<{ token: string }>();
  const { status } = useSession();
  const { workspaceId } = useServices();
  const client = useWorkspaceClient();
  const queryClient = useQueryClient();
  const { spacing } = useTheme();
  const accept = useSubmit(
    async () => {
      const workspace = await client.acceptInvitation(token);
      clearPendingInvite();
      await queryClient.invalidateQueries({ queryKey: ["workspaces"] });
      workspaceId.set(workspace.id);
    },
    (error) =>
      error instanceof ApiError && (error.status === 404 || error.status === 400)
        ? "This invitation is invalid, expired or was already used."
        : describeError(error),
  );

  return (
    <Screen style={{ padding: spacing.xl, gap: spacing.lg, justifyContent: "center" }}>
      <Title>Join a workspace</Title>
      {status === "signedIn" ? (
        <>
          <Body>You&apos;ve been invited to a workspace.</Body>
          <ErrorText message={accept.error} />
          <Button
            title={accept.pending ? "Joining…" : "Accept invitation"}
            disabled={accept.pending}
            onPress={async () => {
              if (await accept.run()) router.replace("/workspaces");
            }}
          />
          <Button
            title="Not now"
            variant="secondary"
            onPress={() => {
              clearPendingInvite();
              router.replace("/");
            }}
          />
        </>
      ) : (
        <>
          <Body>Sign in or create an account to accept this invitation.</Body>
          <Button
            title="Sign in"
            onPress={() => {
              setPendingInvite(token);
              router.replace("/sign-in");
            }}
          />
          <Button
            title="Create an account"
            variant="secondary"
            onPress={() => {
              setPendingInvite(token);
              router.replace("/sign-up");
            }}
          />
        </>
      )}
    </Screen>
  );
}

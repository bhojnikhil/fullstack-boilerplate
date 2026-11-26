import { useState } from "react";
import { ScrollView, Share, View } from "react-native";

import { Button } from "@/components/button";
import { Screen } from "@/components/screen";
import { Body, ErrorText, Muted } from "@/components/ui";
import { useSubmit } from "@/features/auth/use-submit";
import { buildInviteLink } from "@/features/workspaces/invite-link";
import { QrCode } from "@/features/workspaces/qr-code";
import {
  useActiveWorkspace,
  useWorkspaceClient,
} from "@/features/workspaces/use-workspaces";
import { useTheme } from "@/theme/use-theme";

export default function InviteShare() {
  const { spacing } = useTheme();
  const { active } = useActiveWorkspace();
  const client = useWorkspaceClient();
  const [link, setLink] = useState<string | null>(null);
  const create = useSubmit(async () => {
    const invitation = await client.invite(active!.id, "member");
    setLink(buildInviteLink(invitation.token));
  });

  if (!active) {
    return (
      <Screen style={{ padding: spacing.xl }}>
        <Body>Choose a workspace first.</Body>
      </Screen>
    );
  }
  return (
    <Screen edges={["bottom", "left", "right"]}>
      <ScrollView contentContainerStyle={{ padding: spacing.xl, gap: spacing.lg }}>
        <Body>Invite someone to {active.name} with a link or QR code.</Body>
        <ErrorText message={create.error} />
        {link ? (
          <>
            <View style={{ alignItems: "center", gap: spacing.md }}>
              <QrCode value={link} />
              <Body selectable>{link}</Body>
              <Muted>
                Anyone with this link can join. It expires; create a new one if needed.
              </Muted>
            </View>
            <Button
              title="Share link"
              onPress={() =>
                void Share.share({ message: `Join ${active.name}: ${link}` }).catch(
                  () => undefined,
                )
              }
            />
          </>
        ) : null}
        <Button
          title={
            create.pending
              ? "Creating…"
              : link
                ? "Create a new link"
                : "Create invite link"
          }
          variant={link ? "secondary" : "primary"}
          disabled={create.pending}
          onPress={() => void create.run()}
        />
      </ScrollView>
    </Screen>
  );
}

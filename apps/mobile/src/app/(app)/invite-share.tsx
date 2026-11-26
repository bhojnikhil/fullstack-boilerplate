import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ScrollView, Share, View } from "react-native";

import { Button } from "@/components/button";
import { TextField } from "@/components/text-field";
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
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"member" | "admin">("member");
  const invitations = useQuery({
    queryKey: ["invitations", active?.id],
    enabled: !!active,
    queryFn: () => client.invitations(active!.id),
  });
  const [createdLink, setCreatedLink] = useState<{
    workspaceId: string;
    url: string;
  } | null>(null);
  const link =
    createdLink && createdLink.workspaceId === active?.id ? createdLink.url : null;
  const create = useSubmit(async () => {
    const invitation = await client.invite(active!.id, role, email.trim() || undefined);
    if (!email.trim() && !invitation.token)
      throw new Error("The server did not return a link token.");
    setCreatedLink(
      invitation.token
        ? { workspaceId: active!.id, url: buildInviteLink(invitation.token) }
        : null,
    );
    setEmail("");
    await queryClient.invalidateQueries({ queryKey: ["invitations", active!.id] });
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
        <TextField
          label="Email (leave blank for a link)"
          value={email}
          onChangeText={setEmail}
          autoCapitalize="none"
          keyboardType="email-address"
        />
        <Button
          title={`Role: ${role} (tap to change)`}
          variant="secondary"
          onPress={() => setRole(role === "member" ? "admin" : "member")}
        />
        <ErrorText message={create.error} />
        {invitations.error ? <ErrorText message="Couldn't load invitations." /> : null}
        {invitations.data?.map((invitation) => (
          <View key={invitation.id}>
            <Body>
              {invitation.email ?? "Link invitation"} · {invitation.role} ·{" "}
              {invitation.status}
            </Body>
            {invitation.status === "pending" ? (
              <Button
                title="Revoke"
                variant="secondary"
                onPress={() =>
                  void client
                    .revoke(active.id, invitation.id)
                    .then(() =>
                      queryClient.invalidateQueries({
                        queryKey: ["invitations", active.id],
                      }),
                    )
                    .catch(() => undefined)
                }
              />
            ) : null}
          </View>
        ))}
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
                : email.trim()
                  ? "Send email invitation"
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

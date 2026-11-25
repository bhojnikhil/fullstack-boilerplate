import { useQueryClient } from "@tanstack/react-query";
import { router } from "expo-router";
import { useState } from "react";

import { Button } from "@/components/button";
import { KeyboardAvoidingForm } from "@/components/keyboard-avoiding-form";
import { Screen } from "@/components/screen";
import { TextField } from "@/components/text-field";
import { ErrorText } from "@/components/ui";
import { useSubmit } from "@/features/auth/use-submit";
import { useWorkspaceClient } from "@/features/workspaces/use-workspaces";
import { useDiscardChangesGuard } from "@/hooks/use-discard-changes-guard";
import { useServices } from "@/providers/services";

export default function NewWorkspace() {
  const client = useWorkspaceClient();
  const queryClient = useQueryClient();
  const { workspaceId } = useServices();
  const [name, setName] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [timezone, setTimezone] = useState(
    () => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
  );
  const [saved, setSaved] = useState(false);
  useDiscardChangesGuard(!saved && name !== "", () => setName(""));

  const create = useSubmit(async () => {
    const workspace = await client.create({
      name: name.trim(),
      currency: currency.trim().toUpperCase(),
      timezone: timezone.trim(),
    });
    await queryClient.invalidateQueries({ queryKey: ["workspaces"] });
    workspaceId.set(workspace.id);
  });

  return (
    <Screen edges={["bottom", "left", "right"]}>
      <KeyboardAvoidingForm>
        <TextField
          label="Name"
          value={name}
          onChangeText={setName}
          returnKeyType="next"
        />
        <TextField
          label="Currency"
          value={currency}
          onChangeText={setCurrency}
          autoCapitalize="characters"
          maxLength={3}
          hint="Three-letter code, e.g. USD"
        />
        <TextField
          label="Time zone"
          value={timezone}
          onChangeText={setTimezone}
          autoCapitalize="none"
          hint="e.g. America/Chicago"
        />
        <ErrorText message={create.error} />
        <Button
          title={create.pending ? "Creating…" : "Create workspace"}
          disabled={create.pending || !name.trim()}
          onPress={async () => {
            if (await create.run()) {
              setSaved(true);
              router.back();
            }
          }}
        />
      </KeyboardAvoidingForm>
    </Screen>
  );
}

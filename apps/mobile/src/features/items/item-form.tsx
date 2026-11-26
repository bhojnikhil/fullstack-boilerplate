import { useState } from "react";

import { Button } from "@/components/button";
import { KeyboardAvoidingForm } from "@/components/keyboard-avoiding-form";
import { TextField } from "@/components/text-field";
import { ErrorText } from "@/components/ui";
import { useSubmit } from "@/features/auth/use-submit";
import { useDiscardChangesGuard } from "@/hooks/use-discard-changes-guard";
import type { ItemFields } from "@/lib/mutation-queue";

interface ItemFormProps {
  initial?: ItemFields;
  submitLabel: string;
  onSubmit: (fields: ItemFields) => Promise<void>;
  /** Called once saved (the form no longer guards against leaving). */
  onDone: () => void;
  onDelete?: () => void;
}

export function ItemForm({
  initial,
  submitLabel,
  onSubmit,
  onDone,
  onDelete,
}: ItemFormProps) {
  const [title, setTitle] = useState(initial?.title ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [saved, setSaved] = useState(false);
  const dirty =
    title !== (initial?.title ?? "") || description !== (initial?.description ?? "");
  useDiscardChangesGuard(dirty && !saved, () => {
    setTitle(initial?.title ?? "");
    setDescription(initial?.description ?? "");
  });
  const save = useSubmit(async () => {
    await onSubmit({
      title: title.trim(),
      description: description.trim() === "" ? null : description.trim(),
    });
  });

  return (
    <KeyboardAvoidingForm>
      <TextField
        label="Title"
        value={title}
        onChangeText={setTitle}
        maxLength={255}
        returnKeyType="next"
      />
      <TextField
        label="Description"
        value={description}
        onChangeText={setDescription}
        multiline
        returnKeyType="default"
      />
      <ErrorText message={save.error} />
      <Button
        title={save.pending ? "Saving…" : submitLabel}
        disabled={
          save.pending || title.trim() === "" || (initial !== undefined && !dirty)
        }
        onPress={async () => {
          if (await save.run()) {
            setSaved(true);
            onDone();
          }
        }}
      />
      {onDelete ? (
        <Button title="Delete item" variant="secondary" onPress={onDelete} />
      ) : null}
    </KeyboardAvoidingForm>
  );
}

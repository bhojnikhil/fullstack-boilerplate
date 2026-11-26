import { router, useLocalSearchParams } from "expo-router";
import { Alert } from "react-native";

import { Screen } from "@/components/screen";
import { Body } from "@/components/ui";
import { ItemForm } from "@/features/items/item-form";
import { useDeleteItem, useItem, useSaveItem } from "@/features/items/use-items";
import { describeError } from "@/lib/api-error";

export default function EditItem() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const item = useItem(id);
  const { update } = useSaveItem();
  const remove = useDeleteItem();

  if (!item) {
    return (
      <Screen style={{ padding: 24 }}>
        <Body>This item is no longer available.</Body>
      </Screen>
    );
  }
  return (
    <Screen edges={["bottom", "left", "right"]}>
      <ItemForm
        initial={{ title: item.title, description: item.description }}
        submitLabel="Save changes"
        onSubmit={(fields) => update(item, fields)}
        onDone={() => router.back()}
        onDelete={() =>
          Alert.alert("Delete this item?", "This can't be undone.", [
            { text: "Cancel", style: "cancel" },
            {
              text: "Delete",
              style: "destructive",
              onPress: () =>
                remove.mutate(item, {
                  onSuccess: () => router.back(),
                  onError: (error) =>
                    Alert.alert("Couldn't delete", describeError(error)),
                }),
            },
          ])
        }
      />
    </Screen>
  );
}

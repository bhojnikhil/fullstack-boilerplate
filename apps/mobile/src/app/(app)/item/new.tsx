import { router } from "expo-router";

import { Screen } from "@/components/screen";
import { ItemForm } from "@/features/items/item-form";
import { useSaveItem } from "@/features/items/use-items";

export default function NewItem() {
  const { create } = useSaveItem();
  return (
    <Screen edges={["bottom", "left", "right"]}>
      <ItemForm
        submitLabel="Add item"
        onSubmit={async (fields) => {
          await create(fields);
        }}
        onDone={() => router.back()}
      />
    </Screen>
  );
}

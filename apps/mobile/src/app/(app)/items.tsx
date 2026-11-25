import { FlatList, Text, View } from "react-native";

import { Screen } from "@/components/screen";
import { useTheme } from "@/theme/use-theme";

interface Item {
  id: string;
  name: string;
}

// The items API client arrives in phase 9b; until then the list is empty.
const ITEMS: Item[] = [];

export default function Items() {
  const { colors, spacing, typography } = useTheme();
  return (
    <Screen edges={["left", "right"]}>
      <FlatList
        data={ITEMS}
        keyExtractor={(item) => item.id}
        contentContainerStyle={{ flexGrow: 1, padding: spacing.xl }}
        renderItem={({ item }) => (
          <Text style={[typography.body, { color: colors.text }]}>{item.name}</Text>
        )}
        ListEmptyComponent={
          <View
            style={{
              flex: 1,
              justifyContent: "center",
              alignItems: "center",
              gap: spacing.sm,
            }}
          >
            <Text
              accessibilityRole="header"
              style={[typography.heading, { color: colors.text }]}
            >
              No items yet
            </Text>
            <Text
              style={[
                typography.body,
                { color: colors.textMuted, textAlign: "center" },
              ]}
            >
              Items will appear here once the app is connected to the API.
            </Text>
          </View>
        }
      />
    </Screen>
  );
}

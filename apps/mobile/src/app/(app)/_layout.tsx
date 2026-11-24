import Ionicons from "@expo/vector-icons/Ionicons";
import { Tabs } from "expo-router/js-tabs";

import { useTheme } from "@/theme/use-theme";

export default function AppLayout() {
  const { colors } = useTheme();
  const iconColor = (focused: boolean) => (focused ? colors.primary : colors.textMuted);
  return (
    <Tabs
      // Android back from any tab returns to the first tab, then exits.
      backBehavior="initialRoute"
      screenOptions={{
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.textMuted,
      }}
    >
      <Tabs.Screen
        name="items"
        options={{
          title: "Items",
          tabBarAccessibilityLabel: "Items",
          tabBarIcon: ({ focused, size }) => (
            <Ionicons name="list" color={iconColor(focused)} size={size} />
          ),
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: "Settings",
          tabBarAccessibilityLabel: "Settings",
          tabBarIcon: ({ focused, size }) => (
            <Ionicons name="settings-outline" color={iconColor(focused)} size={size} />
          ),
        }}
      />
    </Tabs>
  );
}
